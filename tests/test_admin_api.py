# 이 파일은 관리자 업무 API와 자동 생성 문서가 공통 prefix 밖으로 노출되지 않는지 검증한다.
import unittest

from admin.backend.app import app
from admin.backend.config import ADMIN_API_PREFIX


class AdminApiPrefixTests(unittest.TestCase):
    def test_all_business_api_paths_use_admin_prefix(self) -> None:
        paths = app.openapi()["paths"]

        self.assertTrue(paths)
        self.assertTrue(
            all(path.startswith(f"{ADMIN_API_PREFIX}/") for path in paths),
            paths,
        )

    def test_generated_documentation_paths_use_admin_prefix(self) -> None:
        self.assertEqual(app.openapi_url, f"{ADMIN_API_PREFIX}/openapi.json")
        self.assertEqual(app.docs_url, f"{ADMIN_API_PREFIX}/docs")
        self.assertEqual(app.redoc_url, f"{ADMIN_API_PREFIX}/redoc")
        self.assertEqual(
            app.swagger_ui_oauth2_redirect_url,
            f"{ADMIN_API_PREFIX}/docs/oauth2-redirect",
        )


if __name__ == "__main__":
    unittest.main()
