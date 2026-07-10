# StatYearbook Chat Frontend

React 기반 웹 채팅 클라이언트입니다. 프론트엔드, REST 백엔드, MCP 서버를 분리하는 구조를 전제로 만들었습니다.

채팅 내역은 브라우저 `localStorage`에 저장됩니다. 같은 브라우저에서 다시 접속하면 이전 대화 메시지와 MCP trace가 복원되며, 앱 시작 시에는 새 빈 대화창이 활성화됩니다.

## 실행

```bash
npm install
npm run dev
```

기본값은 목 API입니다. 백엔드가 준비되면 `.env.local`에 아래처럼 지정합니다.

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=false
```

프론트엔드는 `POST /api/chat`을 호출합니다.

```json
{
  "conversationId": "conv-1",
  "message": "경기도 새마을금고 회원 수 연도별 추이를 찾아줘.",
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

요청의 `history`에는 같은 대화창의 최근 대화 5턴이 들어가고, `traces`에는 해당 메시지에 연결된 MCP 요청/응답 내용이 들어갑니다. 응답은 `message`와 `traces`를 포함해야 합니다. `traces`는 MCP 도구 검색, 호출, 응답 내용을 UI에 표시하고 다음 턴의 맥락으로 다시 전달하는 데 사용됩니다.
