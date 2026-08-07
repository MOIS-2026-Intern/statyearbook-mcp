import { useCallback, useEffect, useRef } from "react";

// 바닥에서 이 거리 안쪽이면 사용자가 최신 내용을 보고 있는 것으로 본다.
const PIN_THRESHOLD_PX = 96;

interface StickToBottom {
  // 스크롤이 일어나는 요소에 연결한다.
  viewportRef: (node: HTMLElement | null) => void;
  // 높이가 늘어나는 내용 요소에 연결한다.
  contentRef: (node: HTMLElement | null) => void;
  // 대화를 바꾸는 등 위치를 다시 바닥으로 되돌릴 때 호출한다.
  resetToBottom: () => void;
}

// 내용이 자라는 동안 스크롤을 바닥에 붙여 두되, 사용자가 위로 올리면 놓아준다.
export function useStickToBottom(): StickToBottom {
  const viewport = useRef<HTMLElement | null>(null);
  const observer = useRef<ResizeObserver | null>(null);
  const pinned = useRef(true);

  // 사용자가 위로 올라가 지난 내용을 읽는 중인지 기억한다.
  const handleScroll = useCallback(() => {
    const node = viewport.current;
    if (!node) {
      return;
    }
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    pinned.current = distance <= PIN_THRESHOLD_PX;
  }, []);

  const stick = useCallback(() => {
    const node = viewport.current;
    if (node && pinned.current) {
      node.scrollTop = node.scrollHeight;
    }
  }, []);

  const viewportRef = useCallback(
    (node: HTMLElement | null) => {
      viewport.current?.removeEventListener("scroll", handleScroll);
      viewport.current = node;
      node?.addEventListener("scroll", handleScroll, { passive: true });
    },
    [handleScroll],
  );

  const contentRef = useCallback(
    (node: HTMLElement | null) => {
      observer.current?.disconnect();
      observer.current = null;

      if (!node || typeof ResizeObserver === "undefined") {
        return;
      }
      // 글자가 늘어 내용이 높아질 때마다 같은 만큼 따라 내려간다.
      const next = new ResizeObserver(stick);
      next.observe(node);
      observer.current = next;
    },
    [stick],
  );

  const resetToBottom = useCallback(() => {
    pinned.current = true;
    const node = viewport.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, []);

  useEffect(() => {
    return () => {
      observer.current?.disconnect();
      viewport.current?.removeEventListener("scroll", handleScroll);
    };
  }, [handleScroll]);

  return { viewportRef, contentRef, resetToBottom };
}
