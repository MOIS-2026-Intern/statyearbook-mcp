type JsonRecord = Record<string, unknown>;

// 값이 배열이 아닌 JSON object인지 검사한다.
function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// 수치가 지정된 최솟값과 최댓값 사이에 머물도록 제한한다.
function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum);
}

// 문자열 또는 mark 객체에서 Vega-Lite mark 유형을 추출한다.
function markType(mark: unknown) {
  if (typeof mark === "string") {
    return mark;
  }
  return isRecord(mark) && typeof mark.type === "string" ? mark.type : "";
}

// 단일 mark나 layer에서 뷰의 주요 mark 유형을 찾는다.
function viewMarkType(view: JsonRecord) {
  const direct = markType(view.mark);
  if (direct) {
    return direct;
  }
  if (Array.isArray(view.layer)) {
    for (const layer of view.layer) {
      if (isRecord(layer)) {
        const layered = markType(layer.mark);
        if (layered && layered !== "text") {
          return layered;
        }
      }
    }
  }
  return "";
}

// Vega-Lite 뷰의 인라인 data values를 안전하게 추출한다.
function valuesFrom(view: JsonRecord) {
  const data = view.data;
  return isRecord(data) && Array.isArray(data.values) ? data.values : [];
}

// 카테고리 수, 라벨 길이, 값 편차를 계산해 차트 배치 판단에 사용한다.
function categoryMetrics(view: JsonRecord) {
  const values = valuesFrom(view);
  const labels = [...new Set(values.map((value) => (isRecord(value) ? String(value.x ?? "") : "")))];
  const positiveValues = values
    .map((value) => (isRecord(value) && typeof value.value === "number" ? Math.abs(value.value) : 0))
    .filter((value) => value > 0);
  const minimum = Math.min(...positiveValues);
  const maximum = Math.max(...positiveValues);
  return {
    count: labels.length,
    maxLabelLength: Math.max(0, ...labels.map((label) => [...label].length)),
    valueRatio: positiveValues.length > 1 && minimum > 0 ? maximum / minimum : 1,
  };
}

// 데이터 특성에 따라 막대 방향·크기·라벨 위치를 조정한다.
function styleBar(view: JsonRecord, width: number) {
  const encoding = isRecord(view.encoding) ? { ...view.encoding } : {};
  const { count, maxLabelLength, valueRatio } = categoryMetrics(view);
  const horizontal = count > 8 || maxLabelLength > 14 || valueRatio > 100;

  if (horizontal && isRecord(encoding.x) && isRecord(encoding.y)) {
    const x = encoding.x;
    encoding.x = encoding.y;
    encoding.y = x;
    if ("xOffset" in encoding) {
      encoding.yOffset = encoding.xOffset;
      delete encoding.xOffset;
    }
  }

  return {
    ...view,
    width,
    height: horizontal ? clamp(120 + count * 34, 300, 560) : 340,
    ...(Array.isArray(view.layer)
      ? {
          layer: view.layer.map((layer) => {
            if (!isRecord(layer)) {
              return layer;
            }
            if (markType(layer.mark) === "bar") {
              return { ...layer, mark: { type: "bar", cornerRadiusEnd: 3 } };
            }
            if (horizontal && markType(layer.mark) === "text" && isRecord(layer.mark)) {
              return {
                ...layer,
                mark: { ...layer.mark, dx: 8, dy: 0, align: "left", baseline: "middle" },
              };
            }
            return layer;
          }),
        }
      : { mark: { type: "bar", cornerRadiusEnd: 3 } }),
    encoding,
  };
}

// mark 유형별로 화면 폭에 맞는 뷰 크기와 스타일을 적용한다.
function styleView(view: JsonRecord, width: number): JsonRecord {
  const type = viewMarkType(view);
  if (type === "bar") {
    return styleBar(view, width);
  }
  if (type === "arc") {
    const size = clamp(width, 260, 380);
    return { ...view, width: size, height: size };
  }
  if (type === "rect") {
    const { count } = categoryMetrics(view);
    return { ...view, width, height: clamp(220 + count * 20, 320, 560) };
  }
  return { ...view, width, height: 340 };
}

// 서버의 데이터·인코딩 spec을 보존하면서 화면 폭에 맞는 공통 시각 스타일을 적용한다.
export function applyChartLayout(source: JsonRecord, containerWidth: number): JsonRecord {
  const spec = structuredClone(source);
  const width = clamp(Math.floor(containerWidth - 32), 240, 680);
  const root = spec as JsonRecord;
  const title = typeof root.title === "string" ? root.title : undefined;

  if (Array.isArray(root.vconcat)) {
    root.vconcat = root.vconcat.map((view) => (isRecord(view) ? styleView(view, width) : view));
    root.width = width;
  } else {
    Object.assign(root, styleView(root, width));
  }

  root.padding = 8;
  root.config = {
    ...(isRecord(root.config) ? root.config : {}),
    view: { stroke: null },
    axis: {
      gridColor: "#dde3ea",
      gridOpacity: 0.8,
      labelColor: "#475467",
      labelFontSize: 12,
      titleColor: "#344054",
      titleFontSize: 12,
      titleFontWeight: 600,
      tickColor: "#cbd5e1",
    },
  };
  if (title) {
    root.title = {
      text: title,
      anchor: "start",
      color: "#1f2933",
      fontSize: 14,
      fontWeight: 600,
      offset: 12,
    };
  }
  return root;
}
