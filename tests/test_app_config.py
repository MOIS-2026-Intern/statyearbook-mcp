# -*- coding: utf-8 -*-
"""app 설정이 실행 위치와 무관하게 로컬 모델 경로를 찾는지 검증한다."""
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import REPO_ROOT, embedding_settings_from_env


class LocalModelPathTests(unittest.TestCase):
    # 프로필 기본값의 상대 경로는 저장소 루트 기준으로 해석해야 한다.
    def test_relative_model_path_resolves_from_repo_root(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "STATYEARBOOK_APP_EMBED_PROVIDER": "local",
                "STATYEARBOOK_APP_EMBED_MODEL": "models/bge-m3",
            },
        ):
            settings = embedding_settings_from_env()

        self.assertEqual(settings.model, str(REPO_ROOT / "models" / "bge-m3"))

    # 배포에서 주입하는 절대 경로는 그대로 사용해야 한다.
    def test_absolute_model_path_is_kept(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "STATYEARBOOK_APP_EMBED_PROVIDER": "local",
                "STATYEARBOOK_APP_EMBED_MODEL": "/service/models/bge-m3",
            },
        ):
            settings = embedding_settings_from_env()

        self.assertEqual(settings.model, "/service/models/bge-m3")

    # Hugging Face provider는 경로가 아니라 모델 ID를 그대로 써야 한다.
    def test_huggingface_model_is_not_treated_as_path(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "STATYEARBOOK_APP_EMBED_PROVIDER": "huggingface",
                "STATYEARBOOK_APP_HF_TOKEN": "token",
            },
        ):
            settings = embedding_settings_from_env()

        self.assertFalse(Path(settings.model).is_absolute())


if __name__ == "__main__":
    unittest.main()
