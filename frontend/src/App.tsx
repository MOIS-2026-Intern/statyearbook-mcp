import { useEffect, useMemo, useState } from "react";
import { MoreHorizontal, PanelRightOpen, Share2, Sparkles } from "lucide-react";
import { sendChatMessage } from "./api/chat";
import { ChatMessage } from "./components/ChatMessage";
import { Composer } from "./components/Composer";
import { McpInspector } from "./components/McpInspector";
import { Sidebar } from "./components/Sidebar";
import { seedConversations } from "./data/mockChat";
import { loadConversationState, saveConversationState } from "./storage/conversationStore";
import type { ChatMessage as ChatMessageType, Conversation, McpTrace } from "./types/chat";

const RECENT_HISTORY_TURN_LIMIT = 5;

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

function createUserMessage(content: string): ChatMessageType {
  return {
    id: crypto.randomUUID(),
    role: "user",
    content,
    createdAt: new Date().toISOString(),
  };
}

function createErrorMessage(error: unknown): ChatMessageType {
  const details = error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.";

  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: `REST API 호출 중 오류가 발생했습니다. ${details}`,
    createdAt: new Date().toISOString(),
  };
}

function summarizeTitle(message: string) {
  return message.length > 28 ? `${message.slice(0, 28)}...` : message;
}

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

function getTracesForMessages(messages: ChatMessageType[], traces: McpTrace[]): McpTrace[] {
  const traceIds = new Set(messages.flatMap((message) => message.traceIds ?? []));
  return traces.filter((trace) => traceIds.has(trace.id));
}

function isEmptyConversation(conversation: Conversation) {
  return conversation.messages.length === 0 && conversation.traces.length === 0;
}

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
  return {
    conversations: [nextConversation, ...savedState.conversations],
    activeConversationId: nextConversation.id,
  };
}

export default function App() {
  const [initialConversationState] = useState(createInitialConversationState);
  const [conversations, setConversations] = useState<Conversation[]>(initialConversationState.conversations);
  const [activeConversationId, setActiveConversationId] = useState(initialConversationState.activeConversationId);
  const [isSending, setIsSending] = useState(false);
  const [showMcpTrace, setShowMcpTrace] = useState(true);
  const [modelProfile, setModelProfile] = useState("balanced");

  const activeConversation = conversations.find((conversation) => conversation.id === activeConversationId);

  useEffect(() => {
    saveConversationState(conversations, activeConversationId);
  }, [activeConversationId, conversations]);

  const tracesById = useMemo<Record<string, McpTrace>>(() => {
    return Object.fromEntries((activeConversation?.traces ?? []).map((trace) => [trace.id, trace]));
  }, [activeConversation?.traces]);

  const createNewChat = () => {
    const next = createConversation();
    setConversations((current) => [next, ...current]);
    setActiveConversationId(next.id);
  };

  const sendMessage = async (message: string) => {
    if (!activeConversation) {
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

    setIsSending(true);

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
      setIsSending(false);
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

        <section className="chat-scroll" aria-live="polite">
          {activeConversation.messages.length > 0 ? (
            <div className="message-stack">
              {activeConversation.messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  showMcpTrace={showMcpTrace}
                  tracesById={tracesById}
                />
              ))}
              {isSending ? (
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
            disabled={isSending}
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
