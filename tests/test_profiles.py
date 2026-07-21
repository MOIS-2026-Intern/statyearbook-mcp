import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from admin.backend.config import AdminSettings
from app.config import AppSettings, settings as app_settings
from backend.config import Settings
from utils.embedding import BGE_M3_REVISION, EmbeddingSettings
from utils.env import load_service_env


class ProfileLoaderTests(unittest.TestCase):
    def _service_dir(self, root: str) -> Path:
        service_dir = Path(root)
        profiles = service_dir / "profiles"
        profiles.mkdir()
        for profile in ("local", "test", "main"):
            (profiles / f"{profile}.env").write_text(
                f"SERVICE_VALUE={profile}\nPROFILE_DEFAULT={profile}\n",
                encoding="utf-8",
            )
        return service_dir

    def test_defaults_to_local_profile(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            environ: dict[str, str] = {}

            profile = load_service_env(self._service_dir(root), environ)

        self.assertEqual(profile, "local")
        self.assertEqual(environ["SERVICE_VALUE"], "local")

    def test_os_environment_wins_over_profile_and_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service_dir = self._service_dir(root)
            (service_dir / ".env.test").write_text(
                "SERVICE_VALUE=dotenv\n",
                encoding="utf-8",
            )
            environ = {"APP_PROFILE": "test", "SERVICE_VALUE": "shell"}

            profile = load_service_env(service_dir, environ)

        self.assertEqual(profile, "test")
        self.assertEqual(environ["SERVICE_VALUE"], "shell")
        self.assertEqual(environ["PROFILE_DEFAULT"], "test")

    def test_dotenv_cannot_replace_normalized_selected_profile(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service_dir = self._service_dir(root)
            (service_dir / ".env.test").write_text(
                "APP_PROFILE=main\nSERVICE_VALUE=dotenv\n",
                encoding="utf-8",
            )
            environ = {"APP_PROFILE": " TEST "}

            profile = load_service_env(service_dir, environ)

        self.assertEqual(profile, "test")
        self.assertEqual(environ["APP_PROFILE"], "test")
        self.assertEqual(environ["SERVICE_VALUE"], "dotenv")

    def test_rejects_unknown_profile(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError, "APP_PROFILE"):
                load_service_env(self._service_dir(root), {"APP_PROFILE": "prod"})


class ServiceProfileTests(unittest.TestCase):
    def test_app_non_production_profile_matches_pgvector_schema(self) -> None:
        self.assertIn(app_settings.profile, {"local", "test"})
        self.assertEqual(app_settings.embedding.provider, "local")
        self.assertEqual(app_settings.embedding.dimension, 1024)

    def test_backend_uses_remote_mcp_url(self) -> None:
        settings = Settings()

        self.assertEqual(settings.mcp_url, "http://127.0.0.1:8001/mcp")
        self.assertFalse(hasattr(settings, "mcp_command"))

    def test_platform_port_overrides_service_profile_ports(self) -> None:
        with patch.dict("os.environ", {"PORT": "9999"}):
            app = AppSettings.from_env()
            backend = Settings.from_env()
            admin = AdminSettings.from_env()

        self.assertEqual((app.port, backend.port, admin.port), (9999, 9999, 9999))

    def test_backend_main_profile_requires_frontend_cors_origin(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "CORS_ORIGINS"):
            Settings(
                profile="main",
                openai_api_key="key",
                mcp_url="http://app:8001/mcp",
                cors_origins=[],
            )

    def test_app_main_profile_requires_local_model_artifact(self) -> None:
        embedding = EmbeddingSettings("local", "/missing/bge-m3", 1024)

        with self.assertRaisesRegex(RuntimeError, "model directory not found"):
            AppSettings("main", "postgresql:///main", embedding, "0.0.0.0", 8001)

    def test_app_main_profile_rejects_wrong_bge_manifest_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            model_dir = Path(root) / "bge-m3"
            model_dir.mkdir()
            (model_dir / ".statyearbook-model.json").write_text(
                json.dumps(
                    {
                        "source_model": "BAAI/bge-m3",
                        "revision": BGE_M3_REVISION,
                        "dimension": 768,
                    }
                ),
                encoding="utf-8",
            )
            embedding = EmbeddingSettings(
                "local",
                str(model_dir),
                1024,
                revision=BGE_M3_REVISION,
            )

            with self.assertRaisesRegex(RuntimeError, "manifest dimension"):
                AppSettings("main", "postgresql:///main", embedding, "0.0.0.0", 8001)

    def test_app_and_admin_share_bge_model_identity(self) -> None:
        admin = AdminSettings(profile="local")
        admin_model = admin.embedding_model("bge-m3")

        self.assertEqual(app_settings.embedding.provider, admin_model.provider)
        self.assertEqual(app_settings.embedding.dimension, admin_model.dimension)
        self.assertEqual(app_settings.embedding.max_length, 512)
        self.assertEqual(app_settings.embedding.revision, admin_model.revision)
        self.assertEqual(
            Path(app_settings.embedding.model).resolve(),
            Path(str(admin_model.model)).resolve(),
        )

    def test_admin_profile_enables_exactly_one_database_target(self) -> None:
        local = AdminSettings(profile="local", dsn="postgresql:///local")
        main = AdminSettings(
            profile="main",
            dsn="postgresql:///main",
            api_token="token",
        )

        self.assertEqual(local.target_dsn("local"), "postgresql:///local")
        self.assertEqual(main.target_dsn("production"), "postgresql:///main")
        with self.assertRaises(RuntimeError):
            local.target_dsn("production")

    def test_admin_main_profile_requires_api_token(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "API_TOKEN"):
            AdminSettings(profile="main", dsn="postgresql:///main")


if __name__ == "__main__":
    unittest.main()
