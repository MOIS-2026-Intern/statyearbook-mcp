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

// localStorage의 대화 상태를 검증해 복원하고 실패하면 기본 대화를 사용한다.
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

// 저장 개수를 제한한 대화 상태를 localStorage에 기록한다.
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

// 가장 오래된 대화부터 제거해 저장 개수 한도와 활성 ID를 맞춘다.
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

// 기본 대화 목록을 저장 개수 제한이 적용된 상태로 만든다.
function createFallbackState(conversations: Conversation[]): ConversationState {
  return limitConversationState(conversations, conversations[0]?.id ?? "");
}

// 현재 실행 환경에서 브라우저 localStorage를 사용할 수 있는지 확인한다.
function canUseLocalStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

// 저장소에서 읽은 값이 필수 필드를 갖춘 대화인지 검사한다.
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

// 값이 null이 아닌 객체인지 검사한다.
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

// ISO 시각을 정렬 가능한 타임스탬프로 바꾸고 잘못된 값은 0으로 처리한다.
function toTimestamp(value: string) {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}
