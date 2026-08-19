import { useEffect, useMemo, useRef, useState } from "react";
import { PanelLeftOpen, Sparkles, X } from "lucide-react";
import { fetchChatModels, isChatStoppedError, sendChatMessage } from "./api/chat";
import { ChatMessage } from "./components/ChatMessage";
import { Composer } from "./components/Composer";
import { McpInspector } from "./components/McpInspector";
import { Sidebar } from "./components/Sidebar";
import { StreamingMessage } from "./components/StreamingMessage";
import { MAX_USER_MESSAGES_PER_CONVERSATION, RECENT_HISTORY_TURN_LIMIT } from "./config/chatLimits";
import { WELCOME_CONTENT } from "./config/welcomePrompts";
import { seedConversations } from "./data/mockChat";
import { useStickToBottom } from "./hooks/useStickToBottom";
import { limitConversationState, loadConversationState, saveConversationState } from "./storage/conversationStore";
import { DEFAULT_PUBLICATION_SCOPE } from "./types/chat";
import type {
  ChatMessage as ChatMessageType,
  ChatModelOption,
  ChatProgress,
  Conversation,
  McpTrace,
  PublicationScope,
} from "./types/chat";

// 빈 메시지·trace와 고유 ID를 가진 새 대화를 만든다.
function createConversation(): Conversation {
  const timestamp = new Date().toISOString();

  return {
    id: crypto.randomUUID(),
    title: "새 통계 대화",
    updatedAt: timestamp,
    messages: [],
    traces: [],
  };
}

// 사용자 입력을 현재 시각과 고유 ID가 있는 메시지로 구성한다.
function createUserMessage(content: string, publicationScope: PublicationScope): ChatMessageType {
  return {
    id: crypto.randomUUID(),
    role: "user",
    content,
    createdAt: new Date().toISOString(),
    publicationScope,
  };
}

// API 실패 내용을 대화에 표시할 assistant 메시지로 변환한다.
function createErrorMessage(error: unknown, publicationScope: PublicationScope): ChatMessageType {
  const details = error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.";

  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: `답변 처리 중 오류가 발생했습니다. ${details}`,
    createdAt: new Date().toISOString(),
    publicationScope,
  };
}

// 사용자가 멈춘 응답 자리에 남길 안내 메시지를 만든다. 생성 중이던 본문과 trace는 버린다.
function createStoppedMessage(publicationScope: PublicationScope): ChatMessageType {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "사용자에 의해 응답이 중단되었습니다",
    createdAt: new Date().toISOString(),
    stopped: true,
    publicationScope,
  };
}

// 첫 사용자 메시지를 대화 목록용 짧은 제목으로 줄인다.
function summarizeTitle(message: string) {
  return message.length > 28 ? `${message.slice(0, 28)}...` : message;
}

// 중단 안내는 모델이 만든 답이 아니라 화면용 기록이므로 모델 입력에서 뺀다. 답을 받지 못한
// 질문 자체는 남겨, 중단한 뒤 이어서 물으면 모델이 앞 질문을 알고 답하게 한다.
function excludeStoppedNotices(messages: ChatMessageType[]): ChatMessageType[] {
  return messages.filter((message) => !message.stopped);
}

// 지금 조회 범위에서 주고받은 마지막 구간만 남긴다. 범위를 바꾸면 이전 범위에서 본 내용은
// 새 범위의 근거가 될 수 없다. 전체 범위에서 주요통계집 표를 본 뒤 통계연보로 좁히면, 그 표를
// 기억한 모델이 통계연보에 없는 수치를 그대로 옮겨 적기 때문이다. 범위를 남기지 않은 옛 대화는
// 두 발간물을 모두 볼 수 있는 전체 범위의 대화로 본다.
function getScopedMessages(messages: ChatMessageType[], scope: PublicationScope): ChatMessageType[] {
  let startIndex = messages.length;

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if ((messages[index].publicationScope ?? DEFAULT_PUBLICATION_SCOPE) !== scope) {
      break;
    }
    startIndex = index;
  }

  return messages.slice(startIndex);
}

// 모델에 보낼 최근 사용자 턴부터의 대화 메시지만 선택한다.
function getRecentTurnMessages(messages: ChatMessageType[], maxTurns: number): ChatMessageType[] {
  if (maxTurns <= 0) {
    return [];
  }

  let seenUserTurns = 0;
  let startIndex = 0;

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role !== "user") {
      continue;
    }

    seenUserTurns += 1;
    if (seenUserTurns === maxTurns) {
      startIndex = index;
      break;
    }
  }

  return messages.slice(startIndex);
}

// 선택된 메시지가 참조하는 MCP trace만 필터링한다.
function getTracesForMessages(messages: ChatMessageType[], traces: McpTrace[]): McpTrace[] {
  const traceIds = new Set(messages.flatMap((message) => message.traceIds ?? []));
  return traces.filter((trace) => traceIds.has(trace.id));
}

// 대화의 사용자 질문 수를 계산한다.
function countUserMessages(messages: ChatMessageType[]) {
  return messages.filter((message) => message.role === "user").length;
}

// 메시지와 trace가 모두 없는 새 대화인지 확인한다.
function isEmptyConversation(conversation: Conversation) {
  return conversation.messages.length === 0 && conversation.traces.length === 0;
}

// 저장된 대화를 복원하고 필요하면 새 빈 대화를 앞에 추가한다.
function createInitialConversationState() {
  const savedState = loadConversationState(seedConversations);
  const firstConversation = savedState.conversations[0];

  if (firstConversation && isEmptyConversation(firstConversation)) {
    return {
      conversations: savedState.conversations,
      activeConversationId: firstConversation.id,
    };
  }

  const nextConversation = createConversation();
  return limitConversationState([nextConversation, ...savedState.conversations], nextConversation.id);
}

const MOBILE_VIEWPORT_QUERY = "(max-width: 820px)";

function isMobileViewport() {
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia(MOBILE_VIEWPORT_QUERY).matches;
}

// 데스크톱에서는 양쪽 패널을 바로 보여주되, 모바일에서는 대화 화면부터 보여준다.
function createInitialPanelVisibility() {
  return !isMobileViewport();
}

// 대화 목록·메시지·MCP trace 상태와 주요 UI 흐름을 조정한다.
export default function App() {
  const [initialConversationState] = useState(createInitialConversationState);
  const [conversations, setConversations] = useState<Conversation[]>(initialConversationState.conversations);
  const [activeConversationId, setActiveConversationId] = useState(initialConversationState.activeConversationId);
  const [sendingConversationId, setSendingConversationId] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(createInitialPanelVisibility);
  const [showMcpTrace, setShowMcpTrace] = useState(createInitialPanelVisibility);
  const [publicationScope, setPublicationScope] = useState<PublicationScope>(DEFAULT_PUBLICATION_SCOPE);
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [modelOptionsError, setModelOptionsError] = useState(false);
  const [limitNoticeDismissed, setLimitNoticeDismissed] = useState(false);
  const [progressByConversation, setProgressByConversation] = useState<Record<string, ChatProgress>>({});
  const [streamingByConversation, setStreamingByConversation] = useState<Record<string, string>>({});
  const abortControllerRef = useRef<AbortController | null>(null);
  const { viewportRef, contentRef, resetToBottom } = useStickToBottom();

  const activeConversation = conversations.find((conversation) => conversation.id === activeConversationId);
  const activeConversationIsSending = sendingConversationId === activeConversationId;
  const activeProgress = progressByConversation[activeConversationId];
  const activeStreamingText = streamingByConversation[activeConversationId] ?? "";
  const activeConversationUserMessageCount = activeConversation ? countUserMessages(activeConversation.messages) : 0;
  const conversationMessageLimitReached =
    activeConversationUserMessageCount >= MAX_USER_MESSAGES_PER_CONVERSATION;
  const showConversationLimitNotice =
    conversationMessageLimitReached && !activeConversationIsSending && !limitNoticeDismissed;
  // 첫 화면의 제목과 예시 질의는 지금 고른 조회 범위를 따른다.
  const welcomeContent = WELCOME_CONTENT[publicationScope];

  useEffect(() => {
    saveConversationState(conversations, activeConversationId);
  }, [activeConversationId, conversations]);

  useEffect(() => {
    setLimitNoticeDismissed(false);
  }, [activeConversationId]);

  // 모델 목록은 백엔드 설정을 단일 기준으로 사용한다. 환경에 모델을 추가하면 UI에도
  // 자동으로 나타나며, 현재 선택이 없거나 사라졌으면 백엔드 기본값을 선택한다.
  useEffect(() => {
    const abortController = new AbortController();

    fetchChatModels(abortController.signal)
      .then((catalog) => {
        if (catalog.models.length === 0) {
          throw new Error("No chat models are configured");
        }
        setModelOptions(catalog.models);
        setSelectedModel((current) => (
          catalog.models.some((model) => model.id === current)
            ? current
            : catalog.defaultModel
        ));
        setModelOptionsError(false);
      })
      .catch((error: unknown) => {
        if (!isChatStoppedError(error)) {
          console.error("Failed to load chat models", error);
          setModelOptionsError(true);
        }
      });

    return () => abortController.abort();
  }, []);

  // 데스크톱에서 열린 패널이 화면을 덮은 채 모바일 레이아웃으로 넘어가지 않게 한다.
  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }

    const viewport = window.matchMedia(MOBILE_VIEWPORT_QUERY);
    const closePanelsOnMobile = (event: MediaQueryListEvent) => {
      if (event.matches) {
        setShowSidebar(false);
        setShowMcpTrace(false);
      }
    };

    viewport.addEventListener("change", closePanelsOnMobile);
    return () => viewport.removeEventListener("change", closePanelsOnMobile);
  }, []);

  // 다른 대화로 옮기면 이전 대화에서 위로 올려 둔 위치를 물려받지 않는다.
  useEffect(() => {
    resetToBottom();
  }, [activeConversationId, resetToBottom]);

  const tracesById = useMemo<Record<string, McpTrace>>(() => {
    return Object.fromEntries((activeConversation?.traces ?? []).map((trace) => [trace.id, trace]));
  }, [activeConversation?.traces]);

  // 새 대화를 목록 앞에 추가하고 활성 대화로 전환한다.
  const createNewChat = () => {
    const next = createConversation();
    setConversations((current) => limitConversationState([next, ...current], next.id).conversations);
    setActiveConversationId(next.id);
    if (isMobileViewport()) {
      setShowSidebar(false);
    }
  };

  // 모바일에서는 대화 선택 뒤 사이드바를 닫아 바로 메시지를 볼 수 있게 한다.
  const selectConversation = (conversationId: string) => {
    setActiveConversationId(conversationId);
    if (isMobileViewport()) {
      setShowSidebar(false);
    }
  };

  // 좁은 화면에서는 좌우 패널이 서로 겹치지 않도록 하나만 연다.
  const toggleSidebar = () => {
    if (!showSidebar && isMobileViewport()) {
      setShowMcpTrace(false);
    }
    setShowSidebar((value) => !value);
  };

  const toggleMcpTrace = () => {
    if (!showMcpTrace && isMobileViewport()) {
      setShowSidebar(false);
    }
    setShowMcpTrace((value) => !value);
  };

  // 선택한 대화를 삭제하고 필요하면 인접한 대화를 활성화한다.
  const deleteConversation = (conversationId: string) => {
    const deletedIndex = conversations.findIndex((conversation) => conversation.id === conversationId);
    const remainingConversations = conversations.filter((conversation) => conversation.id !== conversationId);
    const nextConversations = remainingConversations.length > 0 ? remainingConversations : [createConversation()];

    setConversations(nextConversations);

    if (activeConversationId === conversationId) {
      const fallbackIndex = Math.min(Math.max(deletedIndex, 0), nextConversations.length - 1);
      setActiveConversationId(nextConversations[fallbackIndex].id);
    }
  };

  // 현재 대화의 질문 수 제한 안내를 닫는다.
  const dismissConversationLimitNotice = () => {
    setLimitNoticeDismissed(true);
  };

  // 사용자 메시지를 반영하고 API 응답 또는 오류를 같은 대화에 추가한다.
  const sendMessage = async (message: string) => {
    if (!activeConversation) {
      return;
    }
    if (conversationMessageLimitReached) {
      return;
    }
    if (!selectedModel) {
      return;
    }

    const userMessage = createUserMessage(message, publicationScope);
    const conversationId = activeConversation.id;
    const shouldRename = activeConversation.messages.length === 0;
    const history = getRecentTurnMessages(
      getScopedMessages(excludeStoppedNotices(activeConversation.messages), publicationScope),
      RECENT_HISTORY_TURN_LIMIT,
    );
    const historyTraces = getTracesForMessages(history, activeConversation.traces);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setConversations((current) =>
      current.map((conversation) =>
        conversation.id === conversationId
          ? {
              ...conversation,
              title: shouldRename ? summarizeTitle(message) : conversation.title,
              updatedAt: userMessage.createdAt,
              messages: [...conversation.messages, userMessage],
            }
          : conversation,
      ),
    );

    setSendingConversationId(conversationId);

    try {
      const response = await sendChatMessage(
        {
          conversationId,
          message,
          model: selectedModel,
          publicationKind: publicationScope,
          includeMcpTrace: true,
          history,
          traces: historyTraces,
        },
        (progress) => {
          setProgressByConversation((current) => ({
            ...current,
            [conversationId]: progress,
          }));
          // 새 단계가 시작되면 직전 단계에서 흘러나온 조각은 최종 답변이 아니므로 비운다.
          setStreamingByConversation((current) => {
            if (!current[conversationId]) {
              return current;
            }
            const next = { ...current };
            delete next[conversationId];
            return next;
          });
        },
        (text) => {
          setStreamingByConversation((current) => ({
            ...current,
            [conversationId]: (current[conversationId] ?? "") + text,
          }));
        },
        abortController.signal,
      );

      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === conversationId
            ? {
                ...conversation,
                updatedAt: response.message.createdAt,
                messages: [...conversation.messages, { ...response.message, publicationScope }],
                traces: [...conversation.traces, ...response.traces],
              }
            : conversation,
        ),
      );
    } catch (error) {
      // 멈춤 버튼으로 끊은 요청은 오류가 아니다. 받다 만 본문과 trace는 버리고 안내만 남긴다.
      const resultMessage = isChatStoppedError(error)
        ? createStoppedMessage(publicationScope)
        : createErrorMessage(error, publicationScope);

      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === conversationId
            ? {
                ...conversation,
                updatedAt: resultMessage.createdAt,
                messages: [...conversation.messages, resultMessage],
              }
            : conversation,
        ),
      );
    } finally {
      if (abortControllerRef.current === abortController) {
        abortControllerRef.current = null;
      }
      setSendingConversationId((current) => (current === conversationId ? null : current));
      setProgressByConversation((current) => {
        const next = { ...current };
        delete next[conversationId];
        return next;
      });
      setStreamingByConversation((current) => {
        const next = { ...current };
        delete next[conversationId];
        return next;
      });
    }
  };

  // 스트림을 끊어 backend의 추론·도구 호출까지 함께 멈춘다. 뒷정리는 sendMessage가 맡는다.
  const stopMessage = () => {
    abortControllerRef.current?.abort();
  };

  if (!activeConversation) {
    return null;
  }

  return (
    <div
      className={`app-shell${showSidebar ? " app-shell--with-sidebar" : ""}${showMcpTrace ? " app-shell--with-inspector" : ""}`}
    >
      {showSidebar ? (
        <Sidebar
          activeConversationId={activeConversationId}
          conversations={conversations}
          onClose={() => setShowSidebar(false)}
          onCreateConversation={createNewChat}
          onDeleteConversation={deleteConversation}
          onSelectConversation={selectConversation}
        />
      ) : null}

      <main className="chat-layout">
        <header className="chat-header">
          <div className="chat-header__identity">
            {!showSidebar ? (
              <button
                className="icon-button"
                type="button"
                onClick={toggleSidebar}
                aria-label="대화 사이드바 열기"
                title="대화 사이드바 열기"
              >
                <PanelLeftOpen size={18} />
              </button>
            ) : null}
            <div>
              <span className="section-label">통계연보 MCP</span>
              <h1>{activeConversation.title}</h1>
            </div>
          </div>
          <div className="chat-header__actions">
            <button
              className={`mcp-toggle ${showMcpTrace ? "mcp-toggle--active" : ""}`}
              type="button"
              onClick={toggleMcpTrace}
              aria-expanded={showMcpTrace}
              aria-controls="mcp-inspector"
            >
              <Sparkles size={16} />
              <span>MCP 보기</span>
            </button>
          </div>
        </header>

        {showConversationLimitNotice ? (
          <div className="conversation-limit-notice" key={activeConversationId} role="status">
            <div>
              <strong>질문 제한 도달</strong>
              <span>
                이 대화창은 질문 {MAX_USER_MESSAGES_PER_CONVERSATION}개 제한에 도달했습니다. 새 채팅창을 열어
                이어서 질문하세요.
              </span>
            </div>
            <button
              aria-label="질문 제한 안내 닫기"
              className="conversation-limit-notice__close"
              onClick={dismissConversationLimitNotice}
              type="button"
            >
              <X size={18} />
            </button>
          </div>
        ) : null}

        <section className="chat-scroll" aria-live="polite" ref={viewportRef}>
          {activeConversation.messages.length > 0 ? (
            <div className="message-stack" ref={contentRef}>
              {activeConversation.messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  showMcpTrace={showMcpTrace}
                  tracesById={tracesById}
                />
              ))}
              {activeStreamingText ? <StreamingMessage text={activeStreamingText} /> : null}
              {activeConversationIsSending ? (
                <div className="thinking-row" role="status">
                  <span />
                  <p>{activeProgress?.message ?? "요청을 전달하는 중입니다."}</p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="welcome">
              <span className="welcome__badge">LLM + MCP Server</span>
              <h2>
                <span className="welcome__title-name">{welcomeContent.titleName}</span>
                {welcomeContent.titleParticle} 대화로 탐색하세요
              </h2>
              <p>통계 검색부터 원자료 확인, 시각화까지 편하게 대화로 요청해 보세요.</p>
              <div className="prompt-grid">
                {welcomeContent.prompts.map((prompt) => (
                  <button key={prompt.query} type="button" onClick={() => sendMessage(prompt.query)}>
                    {prompt.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        <footer className="composer-wrap">
          <Composer
            disabled={activeConversationIsSending || conversationMessageLimitReached || !selectedModel}
            modelOptions={modelOptions}
            modelOptionsError={modelOptionsError}
            selectedModel={selectedModel}
            onSelectedModelChange={setSelectedModel}
            publicationScope={publicationScope}
            onPublicationScopeChange={setPublicationScope}
            sending={activeConversationIsSending}
            onSendMessage={sendMessage}
            onStopMessage={stopMessage}
          />
          <p>AI 응답은 오류가 있을 수 있습니다. 중요한 통계는 원자료와 함께 확인하세요.</p>
        </footer>
      </main>

      {showMcpTrace ? (
        <McpInspector traces={activeConversation.traces} onClose={() => setShowMcpTrace(false)} />
      ) : null}
    </div>
  );
}
