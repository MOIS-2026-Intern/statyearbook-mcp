import { MessageSquarePlus, PanelLeftClose } from "lucide-react";
import type { Conversation } from "../types/chat";
import { ConversationListItem } from "./ConversationListItem";

interface SidebarProps {
  conversations: Conversation[];
  activeConversationId: string;
  onClose: () => void;
  onCreateConversation: () => void;
  onDeleteConversation: (conversationId: string) => void;
  onSelectConversation: (conversationId: string) => void;
}

// 대화 목록과 새 채팅·선택·삭제 동작을 사이드바에 표시한다.
export function Sidebar({
  conversations,
  activeConversationId,
  onClose,
  onCreateConversation,
  onDeleteConversation,
  onSelectConversation,
}: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="대화 목록">
      <div className="sidebar__brand">
        <div>
          <span className="sidebar__eyebrow">행정안전부</span>
          <strong>통계연보 채팅 서비스</strong>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={onClose}
          aria-label="대화 사이드바 닫기"
          title="대화 사이드바 닫기"
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      <div className="sidebar__actions">
        <button className="nav-button nav-button--primary" type="button" onClick={onCreateConversation}>
          <MessageSquarePlus size={18} />
          <span>새 채팅</span>
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
    </aside>
  );
}
