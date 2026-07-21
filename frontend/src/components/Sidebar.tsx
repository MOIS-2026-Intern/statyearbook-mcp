import { MessageSquarePlus, Search, Database, BarChart3, Settings2 } from "lucide-react";
import type { Conversation } from "../types/chat";
import { ConversationListItem } from "./ConversationListItem";

interface SidebarProps {
  conversations: Conversation[];
  activeConversationId: string;
  onCreateConversation: () => void;
  onDeleteConversation: (conversationId: string) => void;
  onSelectConversation: (conversationId: string) => void;
}

// 대화 목록과 새 채팅·선택·삭제 동작을 사이드바에 표시한다.
export function Sidebar({
  conversations,
  activeConversationId,
  onCreateConversation,
  onDeleteConversation,
  onSelectConversation,
}: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="대화 목록">
      <div className="sidebar__brand">
        <div>
          <span className="sidebar__eyebrow">MOIS</span>
          <strong>StatYearbook</strong>
        </div>
        <button className="icon-button" type="button" aria-label="설정" title="설정">
          <Settings2 size={18} />
        </button>
      </div>

      <div className="sidebar__actions">
        <button className="nav-button nav-button--primary" type="button" onClick={onCreateConversation}>
          <MessageSquarePlus size={18} />
          <span>새 채팅</span>
        </button>
        <button className="nav-button" type="button">
          <Search size={18} />
          <span>채팅 검색</span>
        </button>
        <button className="nav-button" type="button">
          <Database size={18} />
          <span>MCP 서버</span>
        </button>
        <button className="nav-button" type="button">
          <BarChart3 size={18} />
          <span>시각화 결과</span>
        </button>
      </div>

      <div className="conversation-list">
        <div className="section-label">최근 대화</div>
        {conversations.map((conversation) => (
          <ConversationListItem
            conversation={conversation}
            isActive={conversation.id === activeConversationId}
            key={conversation.id}
            onDelete={onDeleteConversation}
            onSelect={onSelectConversation}
          />
        ))}
      </div>

      <div className="sidebar__footer">
        <div className="avatar" aria-hidden="true">
          S
        </div>
        <div>
          <strong>Song</strong>
          <span>GPT API Host</span>
        </div>
      </div>
    </aside>
  );
}
