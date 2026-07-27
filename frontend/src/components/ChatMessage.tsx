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

// 값이 배열이 아닌 일반 객체인지 검사한다.
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

interface ChartResult {
  key: string;
  spec: Record<string, unknown>;
}

// 유효한 visualize trace에서 Vega-Lite 사양과, 재시도·중복 판별용 호출 식별자를 뽑는다.
function vegaLiteSpec(trace: McpTrace): ChartResult | null {
  if (trace.tool !== "visualize" || !isRecord(trace.response)) {
    return null;
  }
  const structured = trace.response.structuredContent;
  if (!isRecord(structured) || !isRecord(structured.vega_lite)) {
    return null;
  }
  const args = isRecord(trace.request) && isRecord(trace.request.arguments)
    ? trace.request.arguments
    : structured.request;
  return { key: JSON.stringify(args ?? {}), spec: structured.vega_lite };
}

// 한 메시지의 visualize 차트를 모으되 같은 호출(재시도·중복)은 마지막 결과만 남기고 서로 다른 시각화는 모두 유지한다.
function messageCharts(traces: McpTrace[]): ChartResult[] {
  const byKey = new Map<string, ChartResult>();
  for (const trace of traces) {
    const chart = vegaLiteSpec(trace);
    if (chart) {
      byKey.set(chart.key, chart);
    }
  }
  return [...byKey.values()];
}

// 사용자·assistant 메시지와 연결된 trace·시각화를 함께 렌더링한다.
export function ChatMessage({ message, tracesById, showMcpTrace }: ChatMessageProps) {
  const [expanded, setExpanded] = useState(false);
  const traces = (message.traceIds ?? []).map((traceId) => tracesById[traceId]).filter(Boolean);
  const charts = messageCharts(traces);
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

        {!isUser && charts.length > 0
          ? charts.map((chart) => <VegaLiteChart key={chart.key} spec={chart.spec} />)
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
