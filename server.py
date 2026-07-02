#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statyearbook MCP 서버 실행 진입점.

행정안전통계연보(statyearbook_mcp DB)를 조회하는 MCP 서버.
MCP 앱 구성/도구/DB 코드는 app/ 패키지 아래에 있고, 여기서는 실행만 한다.

실행:
    pip install -r requirements.txt
    python server.py            # stdio 전송으로 대기 (MCP 클라이언트가 프로세스를 띄움)
"""
from app.mcp_app import main

if __name__ == "__main__":
    main()
