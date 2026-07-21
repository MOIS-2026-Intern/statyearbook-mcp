import { AlertTriangle, CheckCircle2, Circle, Clock3, Loader2 } from "lucide-react";
import type { McpTrace } from "../types/chat";

interface McpTraceCardProps {
  trace: McpTrace;
  dense?: boolean;
  defaultOpen?: boolean;
}

// 값이 배열이 아닌 일반 객체인지 검사한다.
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// JSON object·array로 보이는 텍스트만 파싱하고 일반 문자열은 보존한다.
function tryParseJsonText(value: string) {
  const trimmed = value.trim();
  if (!trimmed || (trimmed[0] !== "{" && trimmed[0] !== "[")) {
    return value;
  }

  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return value;
  }
}

// trace payload 안의 JSON 문자열을 재귀적으로 풀어 표시용 구조로 정규화한다.
function normalizePayloadForDisplay(payload: unknown, key?: string): unknown {
  if (typeof payload === "string") {
    const shouldParseJsonText = key === undefined || key === "text";
    const parsed = shouldParseJsonText ? tryParseJsonText(payload) : payload;
    return parsed === payload ? payload : normalizePayloadForDisplay(parsed);
  }

  if (Array.isArray(payload)) {
    return payload.map((item) => normalizePayloadForDisplay(item));
  }

  if (isRecord(payload)) {
    return Object.fromEntries(
      Object.entries(payload).map(([entryKey, value]) => [entryKey, normalizePayloadForDisplay(value, entryKey)]),
    );
  }

  return payload;
}

// payload 레벨에 맞는 2칸 들여쓰기 문자열을 만든다.
function indent(level: number) {
  return "  ".repeat(level);
}

// 여러 줄 문자열의 마지막 줄에만 구분 문자를 덧붙인다.
function appendSuffixToLastLine(value: string, suffix: string) {
  if (!suffix) {
    return value;
  }

  const lines = value.split("\n");
  lines[lines.length - 1] = `${lines[lines.length - 1]}${suffix}`;
  return lines.join("\n");
}

// 단일·복수 줄 문자열을 trace payload에 적합한 형식으로 표현한다.
function formatString(value: string, level: number) {
  if (!value.includes("\n")) {
    return JSON.stringify(value);
  }

  return `|\n${value
    .split("\n")
    .map((line) => `${indent(level + 1)}${line}`)
    .join("\n")}`;
}

// 임의의 JSON 값을 계층과 줄바꿈을 보존하는 읽기 쉬운 텍스트로 바꾼다.
function formatValue(value: unknown, level = 0): string {
  if (typeof value === "string") {
    return formatString(value, level);
  }

  if (value === null || typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "[]";
    }

    const lines = value.map((item, index) => {
      const suffix = index === value.length - 1 ? "" : ",";
      return `${indent(level + 1)}${appendSuffixToLastLine(formatValue(item, level + 1), suffix)}`;
    });

    return `[\n${lines.join("\n")}\n${indent(level)}]`;
  }

  if (isRecord(value)) {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return "{}";
    }

    const lines = entries.map(([entryKey, entryValue], index) => {
      const suffix = index === entries.length - 1 ? "" : ",";
      return `${indent(level + 1)}${JSON.stringify(entryKey)}: ${appendSuffixToLastLine(
        formatValue(entryValue, level + 1),
        suffix,
      )}`;
    });

    return `{\n${lines.join("\n")}\n${indent(level)}}`;
  }

  return JSON.stringify(value);
}

// trace payload를 정규화한 뒤 화면 표시용 문자열로 변환한다.
function stringifyPayload(payload: unknown) {
  return formatValue(normalizePayloadForDisplay(payload));
}

// trace 상태에 맞는 성공·실행·오류·대기 아이콘을 표시한다.
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

// 값이 있는 MCP 요청 또는 응답 payload를 포맷해 표시한다.
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

// 단일 MCP trace의 상태, 요약, 요청·응답 상세를 카드로 렌더링한다.
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
