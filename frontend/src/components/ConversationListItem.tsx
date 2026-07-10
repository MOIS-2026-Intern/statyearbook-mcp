import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { MoreVertical, Trash2 } from "lucide-react";
import type { Conversation } from "../types/chat";

interface ConversationListItemProps {
  conversation: Conversation;
  isActive: boolean;
  onDelete: (conversationId: string) => void;
  onSelect: (conversationId: string) => void;
}

export function ConversationListItem({
  conversation,
  isActive,
  onDelete,
  onSelect,
}: ConversationListItemProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const itemRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!itemRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);

    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpen]);

  const openContextMenu = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    setMenuOpen(true);
  };

  const deleteConversation = () => {
    setMenuOpen(false);
    onDelete(conversation.id);
  };

  return (
    <div
      className={`conversation-row ${isActive ? "conversation-row--active" : ""} ${
        menuOpen ? "conversation-row--menu-open" : ""
      }`}
      onContextMenu={openContextMenu}
      ref={itemRef}
    >
      <button className="conversation-item" type="button" onClick={() => onSelect(conversation.id)}>
        <span>{conversation.title}</span>
      </button>

      <button
        aria-expanded={menuOpen}
        aria-haspopup="menu"
        aria-label={`${conversation.title} 더 보기`}
        className="conversation-menu-trigger"
        onClick={() => setMenuOpen((value) => !value)}
        title="더 보기"
        type="button"
      >
        <MoreVertical size={17} />
      </button>

      {menuOpen ? (
        <div className="conversation-menu" role="menu">
          <button
            className="conversation-menu__item conversation-menu__item--danger"
            onClick={deleteConversation}
            role="menuitem"
            type="button"
          >
            <Trash2 size={16} />
            <span>삭제</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
