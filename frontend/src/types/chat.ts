export type MessageRole = "user" | "assistant" | "system";
export type PublicationKind = "yearbook" | "major_statistics";
// 화면 버튼이 고르는 조회 범위다. 발간물 하나로 좁히거나 두 발간물을 함께 검색한다.
export type PublicationScope = PublicationKind | "all";

export const DEFAULT_PUBLICATION_SCOPE: PublicationScope = "all";

export type McpTraceKind =
  | "tool_discovery"
  | "tool_call"
  | "tool_result"
  | "resource_read"
  | "error";

export type McpTraceStatus = "queued" | "running" | "success" | "error";

export interface McpTrace {
  id: string;
  kind: McpTraceKind;
  status: McpTraceStatus;
  title: string;
  timestamp: string;
  server: string;
  tool?: string;
  summary?: string;
  durationMs?: number;
  request?: unknown;
  response?: unknown;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  traceIds?: string[];
  // 사용자가 멈춘 턴은 기록으로만 남기고 다음 질의의 모델 입력에서는 제외한다.
  stopped?: boolean;
  // 이 턴을 주고받을 때의 조회 범위다. 범위를 바꾸면 다른 범위의 대화는 모델에 넘기지 않는다.
  publicationScope?: PublicationScope;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
  traces: McpTrace[];
}

export interface ChatRequest {
  conversationId: string;
  message: string;
  model: string;
  // 백엔드 필드 이름은 그대로 두고 값만 조회 범위로 넓힌다.
  publicationKind: PublicationScope;
  includeMcpTrace: boolean;
  history: ChatMessage[];
  traces: McpTrace[];
}

export interface ChatResponse {
  message: ChatMessage;
  traces: McpTrace[];
}

export interface ChatModelOption {
  id: string;
  label: string;
}

export interface ChatModelsResponse {
  defaultModel: string;
  models: ChatModelOption[];
}

export type ChatProgressStage =
  | "connecting_mcp"
  | "discovering_tools"
  | "planning"
  | "calling_tool"
  | "reviewing_results"
  | "finalizing";

export interface ChatProgress {
  stage: ChatProgressStage;
  message: string;
  tool?: string;
}
