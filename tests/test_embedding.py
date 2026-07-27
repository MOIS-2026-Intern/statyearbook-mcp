import json
import os
import sys
import tempfile
import types
import unittest

from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.embedding import (
    BGE_M3_MODEL,
    BGE_M3_REVISION,
    EmbeddingConfigurationError,
    EmbeddingSettings,
    HuggingFaceInferenceProvider,
    LocalSentenceTransformerProvider,
    create_embedding_profile,
)
from app.config import embedding_settings_from_env
from admin.backend.repositories.statistics_embeddings import StatisticsEmbeddingRepository


class ArrayLike(list):
    def tolist(self):
        return list(self)


class EmbeddingSettingsTests(unittest.TestCase):
    def test_defaults_use_local_bge_m3_database_dimension(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = embedding_settings_from_env()

        self.assertEqual(settings.provider, "local")
        self.assertEqual(settings.model, "models/bge-m3")
        self.assertEqual(settings.dimension, 1024)

    def test_bge_m3_identity_is_fixed_while_runtime_options_are_configurable(self) -> None:
        env = {
            "STATYEARBOOK_APP_EMBED_MODEL": "models/bge-m3",
            "STATYEARBOOK_APP_EMBED_BATCH_SIZE": "4",
            "STATYEARBOOK_APP_EMBED_DEVICE": "mps",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = embedding_settings_from_env()

        self.assertEqual(settings.provider, "local")
        self.assertEqual(settings.dimension, 1024)
        self.assertEqual(settings.max_length, 512)
        self.assertEqual(settings.revision, BGE_M3_REVISION)
        self.assertEqual(settings.batch_size, 4)
        self.assertEqual(settings.device, "mps")

    def test_rejects_unknown_embedding_provider(self) -> None:
        with self.assertRaisesRegex(EmbeddingConfigurationError, "provider must be"):
            EmbeddingSettings("remote", "remote-model", 1024)

    def test_huggingface_provider_settings_come_only_from_environment(self) -> None:
        env = {
            "STATYEARBOOK_APP_EMBED_PROVIDER": "huggingface",
            "STATYEARBOOK_APP_HF_TOKEN": "hf_test",
            "STATYEARBOOK_APP_HF_TIMEOUT_SECONDS": "45",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = embedding_settings_from_env()

        self.assertEqual(settings.provider, "huggingface")
        self.assertEqual(settings.model, BGE_M3_MODEL)
        self.assertEqual(settings.revision, BGE_M3_REVISION)
        self.assertEqual(settings.api_token, "hf_test")
        self.assertEqual(settings.timeout_seconds, 45)

    def test_huggingface_provider_requires_token(self) -> None:
        env = {"STATYEARBOOK_APP_EMBED_PROVIDER": "huggingface"}
        with patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(
            EmbeddingConfigurationError, "API token"
        ):
            embedding_settings_from_env()

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

    def test_remote_query_profile_matches_locally_loaded_vectors(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            model_dir = Path(root) / "bge-m3"
            model_dir.mkdir()
            (model_dir / ".statyearbook-model.json").write_text(
                json.dumps(
                    {
                        "source_model": BGE_M3_MODEL,
                        "revision": BGE_M3_REVISION,
                        "dimension": 1024,
                    }
                ),
                encoding="utf-8",
            )
            local = EmbeddingSettings(
                "local", str(model_dir), 1024, revision=BGE_M3_REVISION
            )
            remote = EmbeddingSettings(
                "huggingface",
                BGE_M3_MODEL,
                1024,
                revision=BGE_M3_REVISION,
                api_token="hf_test",
            )

            local_profile = create_embedding_profile(local, "statistics-title-v1")
            remote_profile = create_embedding_profile(remote, "statistics-title-v1")

        self.assertEqual(remote_profile, local_profile)


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


class HuggingFaceEmbeddingProviderTests(unittest.TestCase):
    def _settings(self, batch_size: int = 16) -> EmbeddingSettings:
        return EmbeddingSettings(
            "huggingface",
            BGE_M3_MODEL,
            1024,
            batch_size=batch_size,
            revision=BGE_M3_REVISION,
            api_token="hf_test",
            timeout_seconds=30,
        )

    def test_requests_normalized_bge_m3_embeddings(self) -> None:
        client_class = MagicMock()
        client = client_class.return_value
        vector = [0.0] * 1024
        vector[0] = 0.6
        vector[1] = 0.8
        client.feature_extraction.return_value = ArrayLike([vector])
        fake_module = types.SimpleNamespace(InferenceClient=client_class)

        with patch.dict(sys.modules, {"huggingface_hub": fake_module}):
            provider = HuggingFaceInferenceProvider(self._settings())
            vectors = provider.encode(["행정안전통계연보"])

        self.assertEqual(vectors, [vector])
        client_class.assert_called_once_with(
            provider="hf-inference",
            api_key="hf_test",
            timeout=30,
        )
        client.feature_extraction.assert_called_once_with(
            ["행정안전통계연보"],
            model=BGE_M3_MODEL,
            normalize=True,
            truncate=True,
            truncation_direction="right",
        )

    def test_batches_remote_requests_and_preserves_order(self) -> None:
        client_class = MagicMock()
        client = client_class.return_value
        first = [0.0] * 1024
        second = [0.0] * 1024
        third = [0.0] * 1024
        first[0], second[1], third[2] = 1.0, 1.0, 1.0
        client.feature_extraction.side_effect = [
            ArrayLike([first, second]),
            ArrayLike([third]),
        ]
        fake_module = types.SimpleNamespace(InferenceClient=client_class)

        with patch.dict(sys.modules, {"huggingface_hub": fake_module}):
            provider = HuggingFaceInferenceProvider(self._settings(batch_size=2))
            vectors = provider.encode(["one", "two", "three"])

        self.assertEqual(vectors, [first, second, third])
        self.assertEqual(client.feature_extraction.call_count, 2)

    def test_rejects_remote_embedding_with_wrong_dimension(self) -> None:
        client_class = MagicMock()
        client_class.return_value.feature_extraction.return_value = ArrayLike([[0.1, 0.2]])
        fake_module = types.SimpleNamespace(InferenceClient=client_class)

        with patch.dict(sys.modules, {"huggingface_hub": fake_module}):
            provider = HuggingFaceInferenceProvider(self._settings())
            with self.assertRaisesRegex(RuntimeError, "embedding dimension 2"):
                provider.encode(["query"])


class DatabaseDimensionTests(unittest.TestCase):
    def test_embedding_inputs_separate_level4_and_hierarchy_with_70_30_weights(self) -> None:
        row = {
            "chapter": "디지털정부",
            "section": "디지털 정책과 서비스",
            "level3_title": "모바일 신분증",
            "level4_title": "모바일 공무원증",
            "title_ko": "모바일 공무원증",
            "title_en": "Mobile Identification for Public Officials",
        }

        inputs = StatisticsEmbeddingRepository().select_embedding_texts([row])
        groups = inputs.groups

        self.assertEqual([weight for weight, _texts in groups], [0.7, 0.3])
        self.assertEqual(groups[0][1], ["모바일 공무원증 Mobile Identification for Public Officials"])
        self.assertEqual(
            groups[1][1],
            ["모바일 신분증 디지털 정책과 서비스 디지털정부"],
        )

    def test_rejects_model_before_writing_to_wrong_vector_dimension(self) -> None:
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"format_type": "vector(1536)"}

        with self.assertRaisesRegex(
            EmbeddingConfigurationError,
            r"vector\(1536\).*vector\(1024\)",
        ):
            StatisticsEmbeddingRepository().select_and_validate_dimension(conn, 1024)

    def test_accepts_matching_vector_dimension(self) -> None:
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"format_type": "vector(1024)"}

        StatisticsEmbeddingRepository().select_and_validate_dimension(conn, 1024)


if __name__ == "__main__":
    unittest.main()
