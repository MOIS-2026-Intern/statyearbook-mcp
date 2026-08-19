import { FormEvent, KeyboardEvent, useState } from "react";
import { BookOpen, DatabaseZap, FileText, Library, SendHorizontal, Square } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ChatModelOption, PublicationScope } from "../types/chat";

interface ScopeOption {
  value: PublicationScope;
  label: string;
  title: string;
  icon: LucideIcon;
}

// 조회 범위 버튼은 넓은 범위부터 좁은 범위 순으로 놓고 기본값인 전체를 맨 앞에 둔다.
const SCOPE_OPTIONS: ScopeOption[] = [
  { value: "all", label: "전체", title: "통계연보와 주요통계집 함께 조회", icon: Library },
  { value: "yearbook", label: "통계연보", title: "통계연보만 조회", icon: BookOpen },
  { value: "major_statistics", label: "주요통계집", title: "주요통계집만 조회", icon: FileText },
];

interface ComposerProps {
  disabled: boolean;
  sending: boolean;
  modelOptions: ChatModelOption[];
  modelOptionsError: boolean;
  selectedModel: string;
  onSelectedModelChange: (model: string) => void;
  publicationScope: PublicationScope;
  onPublicationScopeChange: (scope: PublicationScope) => void;
  onSendMessage: (message: string) => void;
  onStopMessage: () => void;
}

// 메시지 입력, 조회 범위 선택, 전송 상태를 관리하는 작성기를 렌더링한다.
export function Composer({
  disabled,
  sending,
  modelOptions,
  modelOptionsError,
  selectedModel,
  onSelectedModelChange,
  publicationScope,
  onPublicationScopeChange,
  onSendMessage,
  onStopMessage,
}: ComposerProps) {
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
        placeholder="통계자료에 대해 물어보세요..."
        rows={1}
        value={value}
      />

      <div className="composer__bar">
        <div className="composer__tools">
          <div className="publication-switch" role="group" aria-label="조회 범위">
            {SCOPE_OPTIONS.map((option) => {
              const active = publicationScope === option.value;
              const Icon = option.icon;

              return (
                <button
                  key={option.value}
                  className={active ? "publication-switch__button publication-switch__button--active" : "publication-switch__button"}
                  type="button"
                  aria-pressed={active}
                  disabled={disabled}
                  onClick={() => onPublicationScopeChange(option.value)}
                  title={option.title}
                >
                  <Icon size={15} />
                  <span>{option.label}</span>
                </button>
              );
            })}
          </div>
          <button className="tool-chip" type="button">
            <DatabaseZap size={16} />
            <span>MCP 추적</span>
          </button>
        </div>

        <div className="composer__actions">
          <label className="model-select">
            <span className="sr-only">대화 모델</span>
            <select
              aria-label="대화 모델"
              disabled={disabled || modelOptions.length === 0}
              value={selectedModel}
              onChange={(event) => onSelectedModelChange(event.target.value)}
            >
              {modelOptions.length === 0 ? (
                <option value="">
                  {modelOptionsError ? "모델 목록 오류" : "모델 불러오는 중"}
                </option>
              ) : modelOptions.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                </option>
              ))}
            </select>
          </label>
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
