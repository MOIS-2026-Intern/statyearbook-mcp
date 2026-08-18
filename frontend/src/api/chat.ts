import { createMockAssistantResponse } from "../data/mockChat";
import type { ChatModelsResponse, ChatProgress, ChatRequest, ChatResponse } from "../types/chat";

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

const mockModels: ChatModelsResponse = {
  defaultModel: "openai/gpt-5-mini",
  models: [
    { id: "openai/gpt-5-mini", label: "GPT-5 mini" },
    { id: "anthropic/claude-sonnet-5", label: "Claude Sonnet 5" },
  ],
};

// 사용자가 멈춘 요청과 실제 오류를 호출한 쪽에서 구분한다.
export function isChatStoppedError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

// 백엔드가 허용한 모델 목록과 기본 선택값을 불러온다.
export async function fetchChatModels(signal?: AbortSignal): Promise<ChatModelsResponse> {
  if (useMockApi) {
    return mockModels;
  }
  if (!apiBaseUrl) {
    throw new Error("VITE_BACKEND_BASE_URL is not configured");
  }

  const response = await fetch(`${apiBaseUrl}/api/models`, { signal });
  if (!response.ok) {
    throw new Error(`Model API request failed with ${response.status}`);
  }

  return response.json() as Promise<ChatModelsResponse>;
}

// 프로필 설정에 따라 mock 응답 또는 백엔드 진행 상태 스트림을 호출한다.
export async function sendChatMessage(
  request: ChatRequest,
  onProgress?: (progress: ChatProgress) => void,
  onDelta?: (text: string) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  signal?.throwIfAborted();

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
    // 멈춤 버튼은 이 연결을 끊는다. backend는 끊긴 연결을 보고 추론과 도구 호출을 취소한다.
    signal,
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
