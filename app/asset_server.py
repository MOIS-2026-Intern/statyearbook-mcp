# -*- coding: utf-8 -*-
import threading
from errno import EADDRINUSE
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app import config

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_lock = threading.Lock()
_base_url: str | None = None


# 렌더링 PNG를 저장/서빙할 디렉터리를 만들어 돌려준다.
def visualization_dir() -> Path:
    path = Path(config.VISUALIZATION_DIR).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


# stdio 전송을 오염시키지 않도록 접근 로그를 죽인다.
class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D401
        pass


def _handler():
    directory = str(visualization_dir())
    return partial(_QuietHandler, directory=directory)


def _bind_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), _handler())


# PNG 정적 서버를 한 번만 띄우고 base URL을 돌려준다.
def ensure_asset_server() -> str | None:
    global _base_url
    with _lock:
        if _base_url is not None:
            return _base_url

        # 외부에서 이미 서빙 중이면 서버를 띄우지 않고 URL만 사용한다.
        if config.PUBLIC_BASE_URL:
            visualization_dir()
            _base_url = config.PUBLIC_BASE_URL.rstrip("/")
            return _base_url

        host = config.ASSET_SERVER_HOST
        try:
            httpd = _bind_server(host, config.ASSET_SERVER_PORT)
        except OSError:
            # 포트 충돌 시 임시 포트로 다시 바인딩한다.
            httpd = _bind_server(host, 0)

        port = httpd.server_address[1]
        threading.Thread(
            target=httpd.serve_forever,
            daemon=True,
            name="statyearbook-assets",
        ).start()
        _base_url = f"http://{host}:{port}"
        return _base_url


# 파일명으로 접근 가능한 HTTP URL을 만든다.
def build_asset_url(filename: str) -> str | None:
    base = ensure_asset_server()
    if not base:
        return None
    return f"{base}/{filename}"


# PNG 정적 서버를 단독 프로세스로 실행한다.
def main() -> None:
    host = config.ASSET_SERVER_HOST
    port = config.ASSET_SERVER_PORT
    try:
        httpd = _bind_server(host, port)
    except OSError as exc:
        if exc.errno == EADDRINUSE:
            print(f"Port already in use: http://{host}:{port}")
            print(f"Check the process with: lsof -nP -iTCP:{port} -sTCP:LISTEN")
            return
        raise

    url = f"http://{host}:{httpd.server_address[1]}"
    print(f"Serving statyearbook visualization assets at {url}")
    print(f"Directory: {visualization_dir()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping statyearbook visualization asset server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
