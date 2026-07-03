import { createMockAssistantResponse } from "../data/mockChat";
import type { ChatRequest, ChatResponse } from "../types/chat";

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
const apiBaseUrl = rawBaseUrl?.replace(/\/$/, "");
const useMockApi = import.meta.env.VITE_USE_MOCK_API !== "false";

export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  if (useMockApi || !apiBaseUrl) {
    return createMockAssistantResponse(request.message);
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
