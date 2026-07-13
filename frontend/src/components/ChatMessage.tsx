import { useState } from "react";
import { Bot, ChevronDown, ChevronRight, UserRound } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as ChatMessageType, McpTrace } from "../types/chat";
import { McpTraceCard } from "./McpTraceCard";
import { VegaLiteChart } from "./VegaLiteChart";

interface ChatMessageProps {
  message: ChatMessageType;
  tracesById: Record<string, McpTrace>;
  showMcpTrace: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function vegaLiteSpec(trace: McpTrace): Record<string, unknown> | null {
  if (trace.tool !== "visualize" || !isRecord(trace.response)) {
    return null;
  }
  const structured = trace.response.structuredContent;
  if (!isRecord(structured) || !isRecord(structured.vega_lite)) {
    return null;
  }
  return structured.vega_lite;
}

export function ChatMessage({ message, tracesById, showMcpTrace }: ChatMessageProps) {
  const [expanded, setExpanded] = useState(false);
  const traces = (message.traceIds ?? []).map((traceId) => tracesById[traceId]).filter(Boolean);
  const chartKeys = new Set<string>();
  const charts = traces
    .map(vegaLiteSpec)
    .filter((spec): spec is Record<string, unknown> => spec !== null)
    .filter((spec) => {
      const key = JSON.stringify(spec);
      if (chartKeys.has(key)) {
        return false;
      }
      chartKeys.add(key);
      return true;
    });
  const isUser = message.role === "user";

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}>
      {!isUser ? (
        <div className="message-avatar" aria-hidden="true">
          <Bot size={17} />
        </div>
      ) : null}

      <div className={`message ${isUser ? "message--user" : "message--assistant"}`}>
        <div className={`message__content ${isUser ? "message__content--plain" : "message__content--markdown"}`}>
          {isUser ? (
            message.content
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
                table: ({ node: _node, ...props }) => (
                  <div className="markdown-table-scroll">
                    <table {...props} />
                  </div>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>

        {!isUser
          ? charts.map((spec, index) => <VegaLiteChart key={`${message.id}-chart-${index}`} spec={spec} />)
          : null}

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
