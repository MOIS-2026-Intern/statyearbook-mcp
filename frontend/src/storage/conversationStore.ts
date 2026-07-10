import type { Conversation } from "../types/chat";
import { MAX_STORED_CONVERSATIONS } from "../config/chatLimits";

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

    return limitConversationState(conversations, activeConversationId);
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
    const limitedState = limitConversationState(conversations, activeConversationId);
    const state: StoredConversationState = {
      version: 1,
      activeConversationId: limitedState.activeConversationId,
      conversations: limitedState.conversations,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (error) {
    console.warn("Failed to save conversations", error);
  }
}

export function limitConversationState(conversations: Conversation[], activeConversationId: string): ConversationState {
  if (conversations.length <= MAX_STORED_CONVERSATIONS) {
    return {
      activeConversationId,
      conversations,
    };
  }

  const deleteCount = conversations.length - MAX_STORED_CONVERSATIONS;
  const idsToDelete = new Set(
    [...conversations]
      .sort((left, right) => toTimestamp(left.updatedAt) - toTimestamp(right.updatedAt))
      .slice(0, deleteCount)
      .map((conversation) => conversation.id),
  );
  const limitedConversations = conversations.filter((conversation) => !idsToDelete.has(conversation.id));
  const nextActiveConversationId = limitedConversations.some(
    (conversation) => conversation.id === activeConversationId,
  )
    ? activeConversationId
    : limitedConversations[0]?.id ?? "";

  return {
    activeConversationId: nextActiveConversationId,
    conversations: limitedConversations,
  };
}

function createFallbackState(conversations: Conversation[]): ConversationState {
  return limitConversationState(conversations, conversations[0]?.id ?? "");
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

function toTimestamp(value: string) {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}
