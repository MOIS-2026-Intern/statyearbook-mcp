import { Activity, Database, PanelRightClose } from "lucide-react";
import type { McpTrace } from "../types/chat";
import { McpTraceCard } from "./McpTraceCard";

interface McpInspectorProps {
  traces: McpTrace[];
  onClose: () => void;
}

export function McpInspector({ traces, onClose }: McpInspectorProps) {
  const successCount = traces.filter((trace) => trace.status === "success").length;

  return (
    <aside className="mcp-inspector" aria-label="MCP 추적">
      <div className="mcp-inspector__header">
        <div>
          <span className="section-label">MCP Trace</span>
          <strong>도구 요청/응답</strong>
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="MCP 패널 닫기" title="닫기">
          <PanelRightClose size={18} />
        </button>
      </div>

      <div className="trace-summary">
        <div>
          <Activity size={18} />
          <span>총 활동</span>
          <strong>{traces.length}</strong>
        </div>
        <div>
          <Database size={18} />
          <span>완료</span>
          <strong>{successCount}</strong>
        </div>
      </div>

      <div className="mcp-inspector__list">
        {traces.length > 0 ? (
          traces.map((trace) => <McpTraceCard defaultOpen={false} key={trace.id} trace={trace} />)
        ) : (
          <div className="empty-panel">
            <Database size={24} />
            <p>아직 MCP 활동이 없습니다.</p>
            <span>메시지를 보내면 도구 검색, 호출, 응답 내용이 이곳에 표시됩니다.</span>
          </div>
        )}
      </div>
    </aside>
  );
}
