import type { ChatMessage, ChatResponse, Conversation, McpTrace } from "../types/chat";

const now = new Date().toISOString();

export const seedTraces: McpTrace[] = [
  {
    id: "trace-tools",
    kind: "tool_discovery",
    status: "success",
    title: "사용 가능한 MCP 도구 확인",
    timestamp: now,
    server: "statyearbook",
    summary: "5개 도구 로드됨",
    durationMs: 124,
    request: {
      query: "statistics search table visualize statyearbook",
    },
    response: {
      tools: [
        "search_statistics",
        "search_tables",
        "visualize_table",
        "describe_table",
        "list_assets",
      ],
    },
  },
  {
    id: "trace-search",
    kind: "tool_call",
    status: "success",
    title: "통계표 검색",
    timestamp: now,
    server: "statyearbook",
    tool: "search_statistics",
    summary: "새마을금고 회원 수와 관련된 표 후보 3건",
    durationMs: 486,
    request: {
      keyword: "경기도 새마을금고 회원 수 연도별",
      topK: 3,
    },
    response: {
      matches: [
        {
          table: "지역별 새마을금고 현황",
          score: 0.91,
          columns: ["시도", "연도", "금고수", "회원수"],
        },
        {
          table: "새마을금고 주요지표",
          score: 0.84,
        },
      ],
    },
  },
];

export const seedMessages: ChatMessage[] = [
  {
    id: "msg-user-1",
    role: "user",
    content: "경기도 새마을금고 회원 수 연도별 추이 시각화해줘. mcp tool을 사용해.",
    createdAt: now,
  },
  {
    id: "msg-assistant-1",
    role: "assistant",
    content:
      "경기도 새마을금고 회원 수 추이를 찾기 위해 통계표를 검색했습니다. 후보 표 중 `지역별 새마을금고 현황`이 가장 관련성이 높습니다. 백엔드가 연결되면 이 표의 원자료를 가져와 연도별 라인 차트로 시각화할 수 있습니다.",
    createdAt: now,
    traceIds: ["trace-tools", "trace-search"],
  },
];

export const seedConversations: Conversation[] = [
  {
    id: "conv-1",
    title: "경기도 새마을금고 회원 수 연도별 추이",
    updatedAt: now,
    messages: seedMessages,
    traces: seedTraces,
  },
  {
    id: "conv-2",
    title: "인구 이동 통계표 검색",
    updatedAt: "2026-07-02T11:20:00.000Z",
    messages: [],
    traces: [],
  },
  {
    id: "conv-3",
    title: "지방세 징수액 그래프",
    updatedAt: "2026-07-01T16:10:00.000Z",
    messages: [],
    traces: [],
  },
  {
    id: "conv-4",
    title: "행정구역별 공무원 현황",
    updatedAt: "2026-06-29T08:45:00.000Z",
    messages: [],
    traces: [],
  },
];

// 백엔드 없이 UI 흐름을 확인할 수 있는 지연된 mock 채팅 응답을 만든다.
export function createMockAssistantResponse(message: string): Promise<ChatResponse> {
  const timestamp = new Date().toISOString();
  const tracePrefix = crypto.randomUUID();
  const traces: McpTrace[] = [
    {
      id: `${tracePrefix}-discover`,
      kind: "tool_discovery",
      status: "success",
      title: "MCP 도구 목록 조회",
      timestamp,
      server: "statyearbook",
      summary: "검색, 표 조회, 시각화 도구를 확인함",
      durationMs: 96,
      request: {
        capability: "statistics-search",
        userMessage: message,
      },
      response: {
        tools: ["search_statistics", "search_tables", "visualize"],
      },
    },
    {
      id: `${tracePrefix}-search`,
      kind: "tool_call",
      status: "success",
      title: "관련 통계표 검색",
      timestamp,
      server: "statyearbook",
      tool: "search_statistics",
      summary: "사용자 질문과 가장 가까운 통계표 후보를 찾음",
      durationMs: 372,
      request: {
        query: message,
        limit: 5,
      },
      response: {
        candidates: [
          {
            name: "행정안전통계연보 통계표 후보",
            confidence: 0.88,
          },
          {
            name: "연도별 지역 통계 원자료",
            confidence: 0.79,
          },
        ],
      },
    },
    {
      id: `${tracePrefix}-result`,
      kind: "tool_result",
      status: "success",
      title: "응답 초안 구성",
      timestamp,
      server: "gpt-api-host",
      summary: "검색 결과를 자연어 답변에 반영함",
      durationMs: 188,
      response: {
        visibleToUser: true,
        nextAction: "백엔드 REST API 연결 후 실제 MCP 결과 표시",
      },
    },
  ];

  const response: ChatResponse = {
    message: {
      id: crypto.randomUUID(),
      role: "assistant",
      content:
        "프론트엔드 목 응답입니다. 실제 백엔드가 연결되면 이 자리에는 GPT API가 MCP 호스트를 통해 도구를 호출한 결과가 표시됩니다. 오른쪽 MCP 패널과 메시지 안의 활동 카드에서 요청, 응답, 도구 이름, 실행 시간을 함께 확인할 수 있습니다.",
      createdAt: timestamp,
      traceIds: traces.map((trace) => trace.id),
    },
    traces,
  };

  return new Promise((resolve) => {
    window.setTimeout(() => resolve(response), 650);
  });
}
