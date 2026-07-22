import { createMockAssistantResponse } from "../data/mockChat";
import type { ChatRequest, ChatResponse } from "../types/chat";

const rawBaseUrl = import.meta.env.VITE_BACKEND_BASE_URL
  ?? (import.meta.env.MODE === "development" ? "http://127.0.0.1:8000" : undefined);
const apiBaseUrl = rawBaseUrl?.replace(/\/$/, "");
const useMockApi = import.meta.env.VITE_USE_MOCK_API === "true";

// 프로필 설정에 따라 mock 응답 또는 백엔드 채팅 API를 호출한다.
export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  if (useMockApi) {
    return createMockAssistantResponse(request.message);
  }
  if (!apiBaseUrl) {
    throw new Error("VITE_BACKEND_BASE_URL is not configured");
  }

  const response = await fetch(`${apiBaseUrl}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const details = await response.text();
    throw new Error(details || `Chat API request failed with ${response.status}`);
  }

  return response.json() as Promise<ChatResponse>;
}
