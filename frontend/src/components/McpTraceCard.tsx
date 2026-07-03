import { AlertTriangle, CheckCircle2, Circle, Clock3, Loader2 } from "lucide-react";
import type { McpTrace } from "../types/chat";

interface McpTraceCardProps {
  trace: McpTrace;
  dense?: boolean;
  defaultOpen?: boolean;
}

function stringifyPayload(payload: unknown) {
  if (typeof payload === "string") {
    return payload;
  }

  return JSON.stringify(payload, null, 2);
}

function StatusIcon({ status }: { status: McpTrace["status"] }) {
  if (status === "success") {
    return <CheckCircle2 size={16} />;
  }

  if (status === "running") {
    return <Loader2 className="spin" size={16} />;
  }

  if (status === "error") {
    return <AlertTriangle size={16} />;
  }

  return <Circle size={16} />;
}

function PayloadBlock({ label, payload }: { label: string; payload?: unknown }) {
  if (payload === undefined) {
    return null;
  }

  return (
    <div className="payload-block">
      <span>{label}</span>
      <pre>{stringifyPayload(payload)}</pre>
    </div>
  );
}

export function McpTraceCard({ trace, dense = false, defaultOpen = false }: McpTraceCardProps) {
  const meta = [trace.server, trace.tool, trace.durationMs ? `${trace.durationMs}ms` : undefined]
    .filter(Boolean)
    .join(" · ");

  return (
    <article className={`trace-card ${dense ? "trace-card--dense" : ""}`}>
      <div className={`trace-card__status trace-card__status--${trace.status}`}>
        <StatusIcon status={trace.status} />
      </div>
      <div className="trace-card__body">
        <div className="trace-card__header">
          <strong>{trace.title}</strong>
          <span>{meta}</span>
        </div>
        {trace.summary ? <p>{trace.summary}</p> : null}
        <details open={defaultOpen}>
          <summary>
            <Clock3 size={14} />
            요청/응답 보기
          </summary>
          <PayloadBlock label="Request" payload={trace.request} />
          <PayloadBlock label="Response" payload={trace.response} />
        </details>
      </div>
    </article>
  );
}
