import type { Conversation } from "../types/chat";

const STORAGE_KEY = "statyearbook.chat.conversations.v1";

interface StoredConversationState {
  version: 1;
  activeConversationId: string;
  conversations: Conversation[];
}

export interface ConversationState {
  activeConversationId: string;
  conversations: Conversation[];
}

export function loadConversationState(fallbackConversations: Conversation[]): ConversationState {
  const fallback = createFallbackState(fallbackConversations);

  if (!canUseLocalStorage()) {
    return fallback;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return fallback;
    }

    const parsed = JSON.parse(raw) as Partial<StoredConversationState>;
    const conversations = Array.isArray(parsed.conversations)
      ? parsed.conversations.filter(isConversation)
      : [];

    if (conversations.length === 0) {
      return fallback;
    }

    const activeConversationId =
      typeof parsed.activeConversationId === "string" &&
      conversations.some((conversation) => conversation.id === parsed.activeConversationId)
        ? parsed.activeConversationId
        : conversations[0].id;

    return {
      activeConversationId,
      conversations,
    };
  } catch (error) {
    console.warn("Failed to load saved conversations", error);
    return fallback;
  }
}

export function saveConversationState(conversations: Conversation[], activeConversationId: string) {
  if (!canUseLocalStorage()) {
    return;
  }

  try {
    const state: StoredConversationState = {
      version: 1,
      activeConversationId,
      conversations,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (error) {
    console.warn("Failed to save conversations", error);
  }
}

function createFallbackState(conversations: Conversation[]): ConversationState {
  return {
    activeConversationId: conversations[0]?.id ?? "",
    conversations,
  };
}

function canUseLocalStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function isConversation(value: unknown): value is Conversation {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    typeof value.updatedAt === "string" &&
    Array.isArray(value.messages) &&
    Array.isArray(value.traces)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
