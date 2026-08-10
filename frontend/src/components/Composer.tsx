import { FormEvent, KeyboardEvent, useState } from "react";
import { DatabaseZap, Mic, Paperclip, SendHorizontal, Square } from "lucide-react";

interface ComposerProps {
  disabled: boolean;
  sending: boolean;
  onSendMessage: (message: string) => void;
  onStopMessage: () => void;
}

// 메시지 입력과 전송 상태를 관리하는 작성기를 렌더링한다.
export function Composer({ disabled, sending, onSendMessage, onStopMessage }: ComposerProps) {
  const [value, setValue] = useState("");

  // 빈 입력과 비활성 상태를 제외하고 정리된 메시지를 전송한다.
  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = value.trim();

    if (!trimmed || disabled) {
      return;
    }

    onSendMessage(trimmed);
    setValue("");
  };

  // Shift 없는 Enter를 줄바꿈 대신 메시지 전송으로 처리한다.
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      submit(event);
    }
  };

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        aria-label="메시지"
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="행정안전통계연보에 대해 물어보세요..."
        rows={1}
        value={value}
      />

      <div className="composer__bar">
        <div className="composer__tools">
          <button className="icon-button" type="button" aria-label="파일 첨부" title="파일 첨부">
            <Paperclip size={18} />
          </button>
          <button className="tool-chip" type="button">
            <DatabaseZap size={16} />
            <span>MCP 추적</span>
          </button>
        </div>

        <div className="composer__actions">
          <button className="icon-button" type="button" aria-label="음성 입력" title="음성 입력">
            <Mic size={18} />
          </button>
          {sending ? (
            <button
              className="send-button send-button--stop"
              type="button"
              onClick={onStopMessage}
              aria-label="응답 중단"
              title="응답 중단"
            >
              <Square size={13} fill="currentColor" />
            </button>
          ) : (
            <button className="send-button" type="submit" disabled={disabled || !value.trim()} aria-label="전송">
              <SendHorizontal size={19} />
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
