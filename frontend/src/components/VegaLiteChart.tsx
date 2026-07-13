import { useEffect, useMemo, useRef, useState } from "react";
import embed from "vega-embed";
import type { VisualizationSpec } from "vega-embed";
import { applyChartLayout } from "./chartLayout";

interface VegaLiteChartProps {
  spec: Record<string, unknown>;
}

export function VegaLiteChart({ spec }: VegaLiteChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const layoutSpec = useMemo(
    () => (containerWidth > 0 ? applyChartLayout(spec, containerWidth) : null),
    [containerWidth, spec],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    setContainerWidth(Math.floor(container.getBoundingClientRect().width));
    const observer = new ResizeObserver(([entry]) => {
      setContainerWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !layoutSpec) {
      return;
    }

    let disposed = false;
    let finalize: (() => void) | undefined;
    setError(null);

    void embed(container, layoutSpec as VisualizationSpec, {
      actions: {
        export: { png: true, svg: false },
        source: false,
        compiled: false,
        editor: false,
      },
      renderer: "canvas",
      scaleFactor: 2,
    })
      .then((result) => {
        if (disposed) {
          result.finalize();
          return;
        }
        finalize = result.finalize;
      })
      .catch((reason: unknown) => {
        if (!disposed) {
          setError(reason instanceof Error ? reason.message : "차트를 렌더링하지 못했습니다.");
        }
      });

    return () => {
      disposed = true;
      finalize?.();
      container.replaceChildren();
    };
  }, [layoutSpec]);

  return (
    <section className="vega-chart" aria-label="통계 시각화">
      {error ? <p className="vega-chart__error">{error}</p> : null}
      <div className="vega-chart__canvas" ref={containerRef} />
    </section>
  );
}
