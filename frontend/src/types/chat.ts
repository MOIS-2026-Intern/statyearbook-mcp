export type MessageRole = "user" | "assistant" | "system";

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
  modelProfile: string;
  includeMcpTrace: boolean;
  history: ChatMessage[];
  traces: McpTrace[];
}

export interface ChatResponse {
  message: ChatMessage;
  traces: McpTrace[];
}
