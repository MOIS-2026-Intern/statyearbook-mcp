# 이 파일은 관리자 업무 API가 공통 prefix로 노출되는지 검증한다.
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

    def test_publication_management_exposes_select_and_delete_methods(self) -> None:
        publication_api = app.openapi()["paths"][f"{ADMIN_API_PREFIX}/publications"]

        self.assertIn("get", publication_api)
        self.assertIn("delete", publication_api)


if __name__ == "__main__":
    unittest.main()
