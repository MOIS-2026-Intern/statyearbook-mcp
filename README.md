# statyearbook-mcp
행정안전통계연보를 챗봇으로도 만나보세요

## DB 적재 방법
1. parse_yearbook.py가 통계연보 json 파일을 읽어서 db형태에 맞게 json을 재구성하여 parsed_yearbook.json을 생성
2. load_to_postgres.py가 parsed_yearbook.json에 따라 db에 적재
3. embed_statistics.py 가 임베딩 실행하고 db에 적재


```bash
> python load/parse_yearbook.py 통계연보.json
> python load/load_to_postgres.py load/parsed_yearbook.json
> python load/embed_statistics.py
```

## 웹 채팅 실행 구조

- `frontend/`: React 채팅 UI
- `backend/`: FastAPI REST API, OpenAI API 호출, MCP host
- `server.py`: 기존 statyearbook MCP server

백엔드는 프론트의 `POST /api/chat` 요청을 받아 OpenAI Responses API를 호출하고, 모델이 필요하다고 판단한 MCP 도구를 로컬 `server.py`에 stdio로 연결해 실행합니다.

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m backend
```

프론트는 `frontend/.env.local`에 실제 API 주소를 지정한 뒤 실행합니다.

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_USE_MOCK_API=false
```

```bash
cd frontend
npm run dev
```
