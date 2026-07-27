"""MCP app 실행 진입점의 종료 동작을 검증한다."""

import unittest

from unittest.mock import patch

from app import server


class AppServerTests(unittest.TestCase):
    def test_main_exits_cleanly_after_keyboard_interrupt(self) -> None:
        with patch.object(server.mcp, "run", side_effect=KeyboardInterrupt) as run_mock:
            result = server.main()

        self.assertIsNone(result)
        run_mock.assert_called_once_with(transport="streamable-http")

    def test_main_does_not_hide_other_server_errors(self) -> None:
        with patch.object(server.mcp, "run", side_effect=RuntimeError("startup failed")):
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                server.main()


if __name__ == "__main__":
    unittest.main()
