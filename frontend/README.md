# StatYearbook Chat Frontend

React 기반 웹 채팅 클라이언트입니다. 프론트엔드, REST 백엔드, MCP 서버를 분리하는 구조를 전제로 만들었습니다.

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
  "includeMcpTrace": true
}
```

응답은 `message`와 `traces`를 포함해야 합니다. `traces`는 MCP 도구 검색, 호출, 응답 내용을 UI에 표시하는 데 사용됩니다.
