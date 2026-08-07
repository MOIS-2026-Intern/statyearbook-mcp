import { useEffect, useRef, useState } from "react";

// 밀려 있는 글자를 이 시간 안에 따라잡을 속도로 매 프레임 방출량을 정한다.
// 조각이 0.7초 간격으로 오는 실제 패턴에서 다음 조각이 올 때까지 끊기지 않는 값이다.
const CATCH_UP_MS = 300;
// 남은 글자가 적어질수록 느려지므로, 꼬리가 늘어지지 않게 하한을 둔다.
const MIN_CHARS_PER_SECOND = 90;
// 긴 답변이 한꺼번에 밀려도 눈이 따라갈 수 있는 상한이다.
const MAX_CHARS_PER_SECOND = 1200;
// 마크다운을 매번 다시 그려야 하므로 30fps 정도로만 갱신한다.
const MIN_FRAME_MS = 33;
// 탭이 비활성이었다가 돌아왔을 때 밀린 시간을 한 번에 소진하지 않도록 막는다.
const MAX_FRAME_MS = 250;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

// 사용자가 애니메이션을 줄이도록 설정했는지 확인한다.
function prefersReducedMotion() {
  return (
    typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

// 조각이 뭉텅이로 도착해도 화면에는 프레임마다 조금씩 드러내 끊겨 보이지 않게 한다.
export function useSmoothedText(target: string): string {
  const [reducedMotion] = useState(prefersReducedMotion);
  const [smoothed, setSmoothed] = useState("");
  const targetRef = useRef(target);
  const lengthRef = useRef(0);

  useEffect(() => {
    targetRef.current = target;
  }, [target]);

  useEffect(() => {
    if (reducedMotion || typeof requestAnimationFrame !== "function") {
      return;
    }

    let frame = 0;
    let previous = performance.now();

    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);

      const elapsed = now - previous;
      if (elapsed < MIN_FRAME_MS) {
        return;
      }
      previous = now;

      const full = targetRef.current;
      // 다음 단계로 넘어가 버퍼가 비워졌다면 처음부터 다시 드러낸다.
      if (lengthRef.current > full.length) {
        lengthRef.current = 0;
      }

      const pending = full.length - lengthRef.current;
      if (pending === 0) {
        return;
      }

      const perSecond = clamp(
        (pending * 1000) / CATCH_UP_MS,
        MIN_CHARS_PER_SECOND,
        MAX_CHARS_PER_SECOND,
      );
      const chars = Math.max(1, Math.round((perSecond * Math.min(elapsed, MAX_FRAME_MS)) / 1000));

      lengthRef.current = Math.min(full.length, lengthRef.current + chars);
      setSmoothed(full.slice(0, lengthRef.current));
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [reducedMotion]);

  return reducedMotion ? target : smoothed;
}
