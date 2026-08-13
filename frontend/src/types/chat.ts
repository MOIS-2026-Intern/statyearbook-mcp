export type MessageRole = "user" | "assistant" | "system";
export type PublicationKind = "yearbook" | "major_statistics";

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
  publicationKind: PublicationKind;
  includeMcpTrace: boolean;
  history: ChatMessage[];
  traces: McpTrace[];
}

export interface ChatResponse {
  message: ChatMessage;
  traces: McpTrace[];
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
