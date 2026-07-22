import { useEffect, useMemo, useState } from "react";
import { MoreHorizontal, PanelRightOpen, Share2, Sparkles, X } from "lucide-react";
import { sendChatMessage } from "./api/chat";
import { ChatMessage } from "./components/ChatMessage";
import { Composer } from "./components/Composer";
import { McpInspector } from "./components/McpInspector";
import { Sidebar } from "./components/Sidebar";
import { MAX_USER_MESSAGES_PER_CONVERSATION, RECENT_HISTORY_TURN_LIMIT } from "./config/chatLimits";
import { seedConversations } from "./data/mockChat";
import { limitConversationState, loadConversationState, saveConversationState } from "./storage/conversationStore";
import type { ChatMessage as ChatMessageType, Conversation, McpTrace } from "./types/chat";

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
function createUserMessage(content: string): ChatMessageType {
  return {
    id: crypto.randomUUID(),
    role: "user",
    content,
    createdAt: new Date().toISOString(),
  };
}

// API 실패 내용을 대화에 표시할 assistant 메시지로 변환한다.
function createErrorMessage(error: unknown): ChatMessageType {
  const details = error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.";

  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: `REST API 호출 중 오류가 발생했습니다. ${details}`,
    createdAt: new Date().toISOString(),
  };
}

// 첫 사용자 메시지를 대화 목록용 짧은 제목으로 줄인다.
function summarizeTitle(message: string) {
  return message.length > 28 ? `${message.slice(0, 28)}...` : message;
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

// 값이 배열이 아닌 일반 객체인지 검사한다.
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// visualize trace에 프런트엔드가 렌더링할 Vega-Lite 사양이 있는지 확인한다.
function hasVegaLiteSpec(trace: McpTrace) {
  if (trace.tool !== "visualize" || !isRecord(trace.response)) {
    return false;
  }
  const structured = trace.response.structuredContent;
  return isRecord(structured) && isRecord(structured.vega_lite);
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

// 대화 목록·메시지·MCP trace 상태와 주요 UI 흐름을 조정한다.
export default function App() {
  const [initialConversationState] = useState(createInitialConversationState);
  const [conversations, setConversations] = useState<Conversation[]>(initialConversationState.conversations);
  const [activeConversationId, setActiveConversationId] = useState(initialConversationState.activeConversationId);
  const [sendingConversationId, setSendingConversationId] = useState<string | null>(null);
  const [showMcpTrace, setShowMcpTrace] = useState(true);
  const [modelProfile, setModelProfile] = useState("balanced");
  const [limitNoticeDismissed, setLimitNoticeDismissed] = useState(false);

  const activeConversation = conversations.find((conversation) => conversation.id === activeConversationId);
  const activeConversationIsSending = sendingConversationId === activeConversationId;
  const activeConversationUserMessageCount = activeConversation ? countUserMessages(activeConversation.messages) : 0;
  const conversationMessageLimitReached =
    activeConversationUserMessageCount >= MAX_USER_MESSAGES_PER_CONVERSATION;
  const showConversationLimitNotice =
    conversationMessageLimitReached && !activeConversationIsSending && !limitNoticeDismissed;

  useEffect(() => {
    saveConversationState(conversations, activeConversationId);
  }, [activeConversationId, conversations]);

  useEffect(() => {
    setLimitNoticeDismissed(false);
  }, [activeConversationId]);

  const tracesById = useMemo<Record<string, McpTrace>>(() => {
    return Object.fromEntries((activeConversation?.traces ?? []).map((trace) => [trace.id, trace]));
  }, [activeConversation?.traces]);

  const latestVisualizeTraceId = useMemo(() => {
    return [...(activeConversation?.traces ?? [])].reverse().find(hasVegaLiteSpec)?.id;
  }, [activeConversation?.traces]);

  // 새 대화를 목록 앞에 추가하고 활성 대화로 전환한다.
  const createNewChat = () => {
    const next = createConversation();
    setConversations((current) => limitConversationState([next, ...current], next.id).conversations);
    setActiveConversationId(next.id);
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

    const userMessage = createUserMessage(message);
    const conversationId = activeConversation.id;
    const shouldRename = activeConversation.messages.length === 0;
    const history = getRecentTurnMessages(activeConversation.messages, RECENT_HISTORY_TURN_LIMIT);
    const historyTraces = getTracesForMessages(history, activeConversation.traces);

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
      const response = await sendChatMessage({
        conversationId,
        message,
        modelProfile,
        includeMcpTrace: true,
        history,
        traces: historyTraces,
      });

      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === conversationId
            ? {
                ...conversation,
                updatedAt: response.message.createdAt,
                messages: [...conversation.messages, response.message],
                traces: [...conversation.traces, ...response.traces],
              }
            : conversation,
        ),
      );
    } catch (error) {
      const errorMessage = createErrorMessage(error);

      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === conversationId
            ? {
                ...conversation,
                updatedAt: errorMessage.createdAt,
                messages: [...conversation.messages, errorMessage],
              }
            : conversation,
        ),
      );
    } finally {
      setSendingConversationId((current) => (current === conversationId ? null : current));
    }
  };

  if (!activeConversation) {
    return null;
  }

  return (
    <div className={`app-shell ${showMcpTrace ? "app-shell--with-inspector" : ""}`}>
      <Sidebar
        activeConversationId={activeConversationId}
        conversations={conversations}
        onCreateConversation={createNewChat}
        onDeleteConversation={deleteConversation}
        onSelectConversation={setActiveConversationId}
      />

      <main className="chat-layout">
        <header className="chat-header">
          <div>
            <span className="section-label">통계연보 MCP</span>
            <h1>{activeConversation.title}</h1>
          </div>
          <div className="chat-header__actions">
            <button
              className={`mcp-toggle ${showMcpTrace ? "mcp-toggle--active" : ""}`}
              type="button"
              onClick={() => setShowMcpTrace((value) => !value)}
            >
              <Sparkles size={16} />
              <span>MCP 보기</span>
            </button>
            {!showMcpTrace ? (
              <button
                className="icon-button"
                type="button"
                onClick={() => setShowMcpTrace(true)}
                aria-label="MCP 패널 열기"
                title="MCP 패널 열기"
              >
                <PanelRightOpen size={18} />
              </button>
            ) : null}
            <button className="icon-button" type="button" aria-label="공유" title="공유">
              <Share2 size={18} />
            </button>
            <button className="icon-button" type="button" aria-label="더 보기" title="더 보기">
              <MoreHorizontal size={19} />
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

        <section className="chat-scroll" aria-live="polite">
          {activeConversation.messages.length > 0 ? (
            <div className="message-stack">
              {activeConversation.messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  showMcpTrace={showMcpTrace}
                  tracesById={tracesById}
                  latestVisualizeTraceId={latestVisualizeTraceId}
                />
              ))}
              {activeConversationIsSending ? (
                <div className="thinking-row">
                  <span />
                  <p>GPT API 호스트가 MCP 도구 흐름을 구성하는 중입니다.</p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="welcome">
              <span className="welcome__badge">GPT API + MCP Host</span>
              <h2>행정안전통계연보를 대화로 탐색하세요</h2>
              <p>통계표 검색, 원자료 확인, 시각화 요청까지 하나의 대화 흐름에서 처리하는 웹 클라이언트입니다.</p>
              <div className="prompt-grid">
                <button type="button" onClick={() => sendMessage("경기도 새마을금고 회원 수 연도별 추이를 찾아줘.")}>
                  경기도 새마을금고 회원 수 연도별 추이
                </button>
                <button type="button" onClick={() => sendMessage("시도별 인구 이동 통계를 표로 정리해줘.")}>
                  시도별 인구 이동 통계 정리
                </button>
                <button type="button" onClick={() => sendMessage("지방세 징수액을 연도별 그래프로 보고 싶어.")}>
                  지방세 징수액 시각화
                </button>
              </div>
            </div>
          )}
        </section>

        <footer className="composer-wrap">
          <Composer
            disabled={activeConversationIsSending || conversationMessageLimitReached}
            modelProfile={modelProfile}
            onModelProfileChange={setModelProfile}
            onSendMessage={sendMessage}
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
