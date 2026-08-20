# -*- coding: utf-8 -*-
"""app이 실행 인자와 환경변수로 MCP transport를 고르는지 검증한다."""
import io
import unittest
from unittest.mock import patch

from app.server import (
    BANNER_PATH,
    STDIO_TRANSPORT,
    STREAMABLE_HTTP_TRANSPORT,
    main,
    parse_transport,
    print_banner,
)


class TransportSelectionTests(unittest.TestCase):
    # 인자와 환경변수가 없으면 기존 Streamable HTTP 실행을 유지해야 한다.
    def test_default_transport_is_streamable_http(self) -> None:
        with patch.dict("os.environ", {}, clear=False) as environ:
            environ.pop("STATYEARBOOK_APP_TRANSPORT", None)
            self.assertEqual(parse_transport([]), STREAMABLE_HTTP_TRANSPORT)

    # MCP 클라이언트가 직접 실행할 때 쓰는 stdio 인자를 받아야 한다.
    def test_stdio_argument_selects_stdio_transport(self) -> None:
        self.assertEqual(parse_transport(["--transport", "stdio"]), STDIO_TRANSPORT)

    # 인자를 넣기 어려운 실행 환경을 위해 환경변수 기본값도 지원해야 한다.
    def test_environment_variable_sets_default_transport(self) -> None:
        with patch.dict("os.environ", {"STATYEARBOOK_APP_TRANSPORT": "stdio"}):
            self.assertEqual(parse_transport([]), STDIO_TRANSPORT)

    # 알 수 없는 transport 이름은 허용 목록과 함께 즉시 실패해야 한다.
    def test_unknown_environment_transport_fails(self) -> None:
        with patch.dict("os.environ", {"STATYEARBOOK_APP_TRANSPORT": "sse"}):
            with self.assertRaises(RuntimeError):
                parse_transport([])


class BannerStreamTests(unittest.TestCase):
    # 배너는 호출자가 지정한 스트림에 출력해야 한다.
    def test_banner_writes_to_requested_stream(self) -> None:
        stream = io.StringIO()

        print_banner(stream)

        self.assertIn(BANNER_PATH.read_text(encoding="utf-8"), stream.getvalue())

    # stdio에서는 stdout이 JSON-RPC 채널이므로 배너가 stderr로 가야 한다.
    def test_stdio_run_keeps_banner_off_stdout(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            with patch("app.server.mcp.run") as run_mock:
                main(["--transport", "stdio"])

        run_mock.assert_called_once_with(transport=STDIO_TRANSPORT)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(BANNER_PATH.read_text(encoding="utf-8"), stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
