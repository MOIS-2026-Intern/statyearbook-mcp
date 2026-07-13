# StatYearbook Backend

FastAPI 기반 REST 백엔드입니다. 프론트엔드의 `POST /api/chat` 요청을 받아 선택된 채팅 모델 provider를 호출하고, 모델이 요청한 MCP 도구 호출을 로컬 stdio MCP 서버(`server.py`)로 실행합니다.

## 역할

- Frontend: React 채팅 UI
- Backend: REST API, 채팅 모델 provider 호출, MCP host
- MCP server: 행정안전통계연보 도구 제공

## 코드 구조

`backend`는 `Controller -> Service -> Gateway` 흐름으로 나뉩니다. DB repository 대신 외부 시스템 연동을 맡는 `gateway` 계층을 둡니다.

- `controllers/`: FastAPI route와 HTTP request/response 처리
- `services/`: 채팅 use case orchestration
- `gateways/`: 채팅 모델 provider adapter와 MCP stdio server 연동
- `models/tooling.py`: 모델 provider와 MCP host 사이의 내부 표준 `ToolSpec`, `ToolCall`, `ToolResult`
- `models/`: Pydantic request/response DTO
- `serializers/`: MCP 결과와 trace payload 직렬화 보조

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

## 시각화

`visualize` 도구는 `structuredContent.vega_lite`에 Vega-Lite JSON spec을 반환합니다. 프론트엔드는 로컬에 번들된 Vega 라이브러리로 차트를 렌더링하며 PNG 내보내기를 제공합니다. 별도 이미지 저장소나 asset server는 사용하지 않습니다.

## API

### `GET /health`

선택된 모델 provider, 사용 모델, provider 설정 여부, MCP stdio 실행 정보를 확인합니다. 기존 호환성을 위해 `openaiModel`, `openaiConfigured` 필드도 함께 반환합니다.

### `POST /api/chat`

요청:

```json
{
  "conversationId": "conv-1",
  "message": "경기도 새마을금고 회원 수 연도별 추이를 시각화해줘.",
  "modelProfile": "balanced",
  "includeMcpTrace": true,
  "history": [
    {
      "id": "msg-user-1",
      "role": "user",
      "content": "경기도 새마을금고 회원 수 연도별 추이를 찾아줘.",
      "createdAt": "2026-07-09T09:00:00.000Z"
    },
    {
      "id": "msg-assistant-1",
      "role": "assistant",
      "content": "관련 통계표 후보를 찾았습니다.",
      "createdAt": "2026-07-09T09:00:05.000Z",
      "traceIds": ["trace-search-1"]
    }
  ],
  "traces": [
    {
      "id": "trace-search-1",
      "kind": "tool_call",
      "status": "success",
      "title": "search_statistics 호출",
      "timestamp": "2026-07-09T09:00:03.000Z",
      "server": "statyearbook",
      "tool": "search_statistics",
      "request": {"query": "경기도 새마을금고 회원 수"},
      "response": {"count": 1}
    }
  ]
}
```

프론트엔드는 같은 대화창의 최근 대화 5턴과 해당 메시지에 연결된 MCP trace를 `history`, `traces`로 보냅니다. 응답은 프론트엔드가 사용하는 `message`와 `traces` 형식입니다. `traces`에는 MCP 도구 목록 조회, 도구 이름, 요청 인자, 응답 JSON, 실행 시간이 포함됩니다.

백엔드는 HTTP middleware에서 최소 access log를 표준 로거에 남깁니다. 대화 본문, MCP request, MCP response는 운영 로그에 저장하지 않고, 상태 복원은 프론트엔드 저장소가 담당합니다.

## 환경변수

- `STATYEARBOOK_MODEL_PROVIDER`: 채팅 모델 provider, 기본값 `openai`. 현재 값은 `openai`, `local_gemma`를 인식합니다.
- `STATYEARBOOK_CHAT_MODEL`: 채팅 모델, 기본값 `gpt-5.5`
- `OPENAI_API_KEY`: OpenAI provider와 임베딩 생성에 사용하는 API 키
- `STATYEARBOOK_MODEL_TIMEOUT_SECONDS`: 모델 provider 호출 timeout, 기본값 `60`
- `STATYEARBOOK_OPENAI_TIMEOUT_SECONDS`: 기존 OpenAI timeout 변수. `STATYEARBOOK_MODEL_TIMEOUT_SECONDS`가 없을 때 fallback으로 사용합니다.
- `STATYEARBOOK_BACKEND_PORT`: FastAPI 포트, 기본값 `8000`
- `STATYEARBOOK_MCP_COMMAND`: MCP 서버 실행 Python 명령
- `STATYEARBOOK_MCP_ARGS`: MCP 서버 인자, 기본값 `server.py`
- `STATYEARBOOK_MCP_CWD`: MCP 서버 실행 디렉터리

`local_gemma` provider는 adapter 경계가 준비되어 있지만, Ollama, llama.cpp, vLLM 등 실제 로컬 런타임 프로토콜을 정한 뒤 `backend/gateways/local_gemma_gateway.py`에 연결해야 합니다.
