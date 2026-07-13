import { useEffect, useRef, useState } from "react";
import embed from "vega-embed";
import type { VisualizationSpec } from "vega-embed";

interface VegaLiteChartProps {
  spec: Record<string, unknown>;
}

export function VegaLiteChart({ spec }: VegaLiteChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    let disposed = false;
    let finalize: (() => void) | undefined;
    setError(null);

    void embed(container, spec as VisualizationSpec, {
      actions: {
        export: { png: true, svg: false },
        source: false,
        compiled: false,
        editor: false,
      },
      renderer: "canvas",
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
  }, [spec]);

  return (
    <section className="vega-chart" aria-label="통계 시각화">
      {error ? <p className="vega-chart__error">{error}</p> : null}
      <div className="vega-chart__canvas" ref={containerRef} />
    </section>
  );
}
