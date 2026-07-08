# statyearbook-mcp
행정안전통계연보를 챗봇으로도 만나보세요


## 채팅 실행 구조

- `frontend/`: React 채팅 UI
- `backend/`: FastAPI REST API, 채팅 모델 provider adapter, MCP host
- `server.py`: 기존 statyearbook MCP server

백엔드는 프론트의 `POST /api/chat` 요청을 받아 `STATYEARBOOK_MODEL_PROVIDER`로 선택된 모델 host를 호출하고, 모델이 필요하다고 판단한 MCP 도구를 로컬 `server.py`에 stdio로 연결해 실행합니다. 기본 provider는 `openai`입니다.

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
