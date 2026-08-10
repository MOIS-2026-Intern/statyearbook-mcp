# -*- coding: utf-8 -*-
"""채팅 backend가 활성 스트림 때문에 종료를 무기한 기다리지 않는지 검증한다."""
import os
import unittest
from unittest.mock import patch

from backend import main
from backend.config import Settings


class BackendShutdownTests(unittest.TestCase):
    # Uvicorn에 유한한 graceful shutdown 제한 시간을 전달해야 한다.
    @patch("backend.main.uvicorn.run")
    def test_run_limits_graceful_shutdown_wait(self, run_server) -> None:
        main.run()

        timeout = run_server.call_args.kwargs["timeout_graceful_shutdown"]
        self.assertEqual(timeout, main.settings.graceful_shutdown_timeout_seconds)
        self.assertGreater(timeout, 0)

    # 배포 환경에서 종료 대기 시간을 조정할 수 있어야 한다.
    def test_graceful_shutdown_wait_is_configurable(self) -> None:
        with patch.dict(
            os.environ,
            {"STATYEARBOOK_BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS": "2"},
        ):
            configured = Settings.from_env()

        self.assertEqual(configured.graceful_shutdown_timeout_seconds, 2)


if __name__ == "__main__":
    unittest.main()
