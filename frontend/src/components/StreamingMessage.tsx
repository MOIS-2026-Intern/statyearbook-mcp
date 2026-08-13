import { Bot } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSmoothedText } from "../hooks/useSmoothedText";

interface StreamingMessageProps {
  text: string;
}

// 생성 중인 답변을 완성된 메시지와 같은 모양으로 미리 보여준다.
export function StreamingMessage({ text }: StreamingMessageProps) {
  // 조각이 뭉텅이로 도착해도 화면에는 고르게 흘러나오게 한다.
  const smoothed = useSmoothedText(text);

  return (
    <div className="message-row message-row--assistant" aria-busy="true">
      <div className="message-avatar" aria-hidden="true">
        <Bot size={18} />
      </div>
      <div className="message message--assistant message--streaming">
        <div className="message__content message__content--markdown">
          <ReactMarkdown
            remarkPlugins={[[remarkGfm, { singleTilde: false }]]}
            components={{
              a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
              table: ({ node: _node, ...props }) => (
                <div className="markdown-table-scroll">
                  <table {...props} />
                </div>
              ),
            }}
          >
            {smoothed}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
