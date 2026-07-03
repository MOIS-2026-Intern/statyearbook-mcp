# StatYearbook Backend

FastAPI 기반 REST 백엔드입니다. 프론트엔드의 `POST /api/chat` 요청을 받아 OpenAI Responses API를 호출하고, 모델이 요청한 MCP 도구 호출을 로컬 stdio MCP 서버(`server.py`)로 실행합니다.

## 역할

- Frontend: React 채팅 UI
- Backend: REST API, OpenAI API 호출, MCP host
- MCP server: 행정안전통계연보 도구 제공

## 실행

```bash
cd /Users/song/dev/mois/statyearbook-mcp
source .venv/bin/activate
pip install -r requirements.txt
python -m backend
```

서버는 기본적으로 `http://127.0.0.1:8000`에서 실행됩니다.

## 프론트 연결

`frontend/.env.local`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_USE_MOCK_API=false
```

그 다음 프론트엔드를 재시작합니다.

```bash
cd frontend
npm run dev
```

## 시각화 이미지 포트

`visualize` 도구가 만든 PNG는 `STATYEARBOOK_VISUALIZATION_DIR` 디렉터리에 저장됩니다. 브라우저에서 이미지 URL을 계속 열려면 asset server를 별도 터미널에서 실행합니다.

```bash
cd /Users/song/dev/mois/statyearbook-mcp
source .venv/bin/activate
python -m app.asset_server
```

기본 URL은 `http://127.0.0.1:8899`입니다. MCP가 이 고정 URL을 응답에 넣도록 `.env`에 아래 값을 추가합니다.

```bash
STATYEARBOOK_PUBLIC_BASE_URL=http://127.0.0.1:8899
```

이 값을 바꾼 뒤에는 백엔드를 재시작해야 합니다.

## API

### `GET /health`

OpenAI API 키 설정 여부, 사용 모델, MCP stdio 실행 정보를 확인합니다.

### `POST /api/chat`

요청:

```json
{
  "conversationId": "conv-1",
  "message": "경기도 새마을금고 회원 수 연도별 추이를 시각화해줘.",
  "modelProfile": "balanced",
  "includeMcpTrace": true
}
```

응답은 프론트엔드가 사용하는 `message`와 `traces` 형식입니다. `traces`에는 MCP 도구 목록 조회, 도구 이름, 요청 인자, 응답 JSON, 실행 시간이 포함됩니다.

## 환경변수

- `OPENAI_API_KEY`: OpenAI API 키
- `STATYEARBOOK_CHAT_MODEL`: 채팅 모델, 기본값 `gpt-5.5`
- `STATYEARBOOK_BACKEND_PORT`: FastAPI 포트, 기본값 `8000`
- `STATYEARBOOK_MCP_COMMAND`: MCP 서버 실행 Python 명령
- `STATYEARBOOK_MCP_ARGS`: MCP 서버 인자, 기본값 `server.py`
- `STATYEARBOOK_MCP_CWD`: MCP 서버 실행 디렉터리
- `STATYEARBOOK_FORCE_VISUALIZE_NO_INLINE_IMAGE`: `visualize` 호출 시 인라인 이미지 생략
