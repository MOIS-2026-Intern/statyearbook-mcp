import { useState } from "react";
import { Bot, ChevronDown, ChevronRight, UserRound } from "lucide-react";
import type { ChatMessage as ChatMessageType, McpTrace } from "../types/chat";
import { McpTraceCard } from "./McpTraceCard";

interface ChatMessageProps {
  message: ChatMessageType;
  tracesById: Record<string, McpTrace>;
  showMcpTrace: boolean;
}

export function ChatMessage({ message, tracesById, showMcpTrace }: ChatMessageProps) {
  const [expanded, setExpanded] = useState(false);
  const traces = (message.traceIds ?? []).map((traceId) => tracesById[traceId]).filter(Boolean);
  const isUser = message.role === "user";

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}>
      {!isUser ? (
        <div className="message-avatar" aria-hidden="true">
          <Bot size={17} />
        </div>
      ) : null}

      <div className={`message ${isUser ? "message--user" : "message--assistant"}`}>
        <div className="message__content">{message.content}</div>

        {!isUser && showMcpTrace && traces.length > 0 ? (
          <div className="message__trace">
            <button className="trace-toggle" type="button" onClick={() => setExpanded((value) => !value)}>
              {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <span>MCP 활동 {traces.length}건</span>
            </button>
            {expanded ? (
              <div className="message__trace-list">
                {traces.map((trace) => (
                  <McpTraceCard dense key={trace.id} trace={trace} />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {isUser ? (
        <div className="message-avatar message-avatar--user" aria-hidden="true">
          <UserRound size={17} />
        </div>
      ) : null}
    </div>
  );
}
