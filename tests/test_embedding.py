import json
import os
import sys
import tempfile
import types
import unittest

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.embedding import (
    BGE_M3_REVISION,
    EmbeddingConfigurationError,
    EmbeddingSettings,
    LocalSentenceTransformerProvider,
    OpenAIEmbeddingProvider,
    create_embedding_profile,
)
from load.statistics_embedding_source import StatisticsEmbeddingSource


class ArrayLike(list):
    def tolist(self):
        return list(self)


class EmbeddingSettingsTests(unittest.TestCase):
    def test_defaults_preserve_existing_openai_configuration(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = EmbeddingSettings.from_env()

        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.model, "text-embedding-3-small")
        self.assertEqual(settings.dimension, 1536)

    def test_bge_m3_local_defaults_use_pinned_revision(self) -> None:
        env = {
            "STATYEARBOOK_EMBED_PROVIDER": "local",
            "STATYEARBOOK_EMBED_MODEL": "models/bge-m3",
            "STATYEARBOOK_EMBED_DIMENSION": "1024",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = EmbeddingSettings.from_env()

        self.assertEqual(settings.provider, "local")
        self.assertEqual(settings.dimension, 1024)
        self.assertEqual(settings.revision, BGE_M3_REVISION)

    def test_unknown_model_requires_explicit_dimension(self) -> None:
        env = {
            "STATYEARBOOK_EMBED_PROVIDER": "openai",
            "STATYEARBOOK_EMBED_MODEL": "another-model",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(
                EmbeddingConfigurationError,
                "STATYEARBOOK_EMBED_DIMENSION is required",
            ):
                EmbeddingSettings.from_env()

    def test_local_profile_uses_manifest_identity_instead_of_machine_path(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            model_dir = Path(root) / "bge-m3"
            model_dir.mkdir()
            (model_dir / ".statyearbook-model.json").write_text(
                json.dumps(
                    {
                        "source_model": "BAAI/bge-m3",
                        "revision": BGE_M3_REVISION,
                        "dimension": 1024,
                    }
                ),
                encoding="utf-8",
            )
            settings = EmbeddingSettings(
                "local", str(model_dir), 1024, revision=BGE_M3_REVISION
            )

            profile = create_embedding_profile(settings, "statistics-title-v1")

        self.assertEqual(profile.model, "BAAI/bge-m3")
        self.assertEqual(profile.revision, BGE_M3_REVISION)
        self.assertEqual(len(profile.profile_key), 64)


class OpenAIEmbeddingProviderTests(unittest.TestCase):
    @patch("openai.OpenAI")
    def test_uses_configured_model_and_dimension(self, client_class) -> None:
        client = client_class.return_value
        item = MagicMock(embedding=[0.1, 0.2])
        client.embeddings.create.return_value.data = [item]
        settings = EmbeddingSettings("openai", "test-model", 2)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIEmbeddingProvider(settings)
            vectors = provider.encode(["질의"])

        self.assertEqual(vectors, [[0.1, 0.2]])
        client.embeddings.create.assert_called_once_with(
            model="test-model",
            input=["질의"],
            dimensions=2,
        )


class LocalEmbeddingProviderTests(unittest.TestCase):
    def _model_dir(self, root: str, dimension: int = 2) -> Path:
        model_dir = Path(root) / "bge-m3"
        model_dir.mkdir()
        manifest = {
            "source_model": "BAAI/bge-m3",
            "revision": BGE_M3_REVISION,
            "dimension": dimension,
        }
        (model_dir / ".statyearbook-model.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        return model_dir

    def test_rejects_artifact_with_different_revision(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            model_dir = self._model_dir(root)
            settings = EmbeddingSettings(
                "local", str(model_dir), 2, revision="different-revision"
            )

            with self.assertRaisesRegex(
                EmbeddingConfigurationError,
                "manifest revision",
            ):
                LocalSentenceTransformerProvider(settings)

    def test_loads_local_files_only_and_normalizes(self) -> None:
        model_class = MagicMock()
        model = model_class.return_value
        model.encode.return_value = ArrayLike([[0.6, 0.8]])
        fake_module = types.SimpleNamespace(SentenceTransformer=model_class)
        with tempfile.TemporaryDirectory() as root, patch.dict(
            sys.modules,
            {"sentence_transformers": fake_module},
        ):
            model_dir = self._model_dir(root)
            settings = EmbeddingSettings(
                "local",
                str(model_dir),
                2,
                batch_size=4,
                max_length=128,
                revision=BGE_M3_REVISION,
            )
            provider = LocalSentenceTransformerProvider(settings)

            vectors = provider.encode(["행정안전통계연보"])

        self.assertEqual(vectors, [[0.6, 0.8]])
        model_class.assert_called_once_with(
            str(model_dir.resolve()),
            device="cpu",
            local_files_only=True,
        )
        self.assertEqual(model.max_seq_length, 128)
        model.encode.assert_called_once_with(
            ["행정안전통계연보"],
            batch_size=4,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


class DatabaseDimensionTests(unittest.TestCase):
    def test_rejects_model_before_writing_to_wrong_vector_dimension(self) -> None:
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"format_type": "vector(1536)"}

        with self.assertRaisesRegex(
            EmbeddingConfigurationError,
            r"vector\(1536\).*vector\(1024\)",
        ):
            StatisticsEmbeddingSource().validate_dimension(conn, 1024)

    def test_accepts_matching_vector_dimension(self) -> None:
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"format_type": "vector(1024)"}

        StatisticsEmbeddingSource().validate_dimension(conn, 1024)


if __name__ == "__main__":
    unittest.main()
