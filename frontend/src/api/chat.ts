import { createMockAssistantResponse } from "../data/mockChat";
import type { ChatProgress, ChatRequest, ChatResponse } from "../types/chat";

const rawBaseUrl = import.meta.env.VITE_BACKEND_BASE_URL
  ?? (import.meta.env.MODE === "development" ? "http://127.0.0.1:8000" : undefined);
const apiBaseUrl = rawBaseUrl?.replace(/\/$/, "");
const useMockApi = import.meta.env.VITE_USE_MOCK_API === "true";

interface ProgressStreamEvent {
  type: "progress";
  progress: ChatProgress;
}

interface DeltaStreamEvent {
  type: "delta";
  text: string;
}

interface ResultStreamEvent {
  type: "result";
  response: ChatResponse;
}

interface ErrorStreamEvent {
  type: "error";
  error: string;
}

type ChatStreamEvent =
  | ProgressStreamEvent
  | DeltaStreamEvent
  | ResultStreamEvent
  | ErrorStreamEvent;

// 프로필 설정에 따라 mock 응답 또는 백엔드 진행 상태 스트림을 호출한다.
export async function sendChatMessage(
  request: ChatRequest,
  onProgress?: (progress: ChatProgress) => void,
  onDelta?: (text: string) => void,
): Promise<ChatResponse> {
  if (useMockApi) {
    onProgress?.({
      stage: "planning",
      message: "질문을 분석해 필요한 자료를 정하는 중입니다.",
    });
    return createMockAssistantResponse(request.message);
  }
  if (!apiBaseUrl) {
    throw new Error("VITE_BACKEND_BASE_URL is not configured");
  }

  const response = await fetch(`${apiBaseUrl}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Accept": "application/x-ndjson",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const details = await response.text();
    throw new Error(details || `Chat API request failed with ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Chat API did not provide a response stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatResponse | undefined;

  const consumeLine = (line: string) => {
    if (!line.trim()) {
      return;
    }
    const event = JSON.parse(line) as ChatStreamEvent;
    if (event.type === "progress") {
      onProgress?.(event.progress);
      return;
    }
    if (event.type === "delta") {
      onDelta?.(event.text);
      return;
    }
    if (event.type === "error") {
      throw new Error(event.error || "Chat API stream failed");
    }
    if (event.type === "result") {
      result = event.response;
      return;
    }
    throw new Error("Chat API returned an unknown stream event");
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    lines.forEach(consumeLine);

    if (done) {
      break;
    }
  }

  consumeLine(buffer);
  if (!result) {
    throw new Error("Chat API stream ended before the final response");
  }
  return result;
}
