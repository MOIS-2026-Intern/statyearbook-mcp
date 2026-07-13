type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum);
}

function markType(mark: unknown) {
  if (typeof mark === "string") {
    return mark;
  }
  return isRecord(mark) && typeof mark.type === "string" ? mark.type : "";
}

function valuesFrom(view: JsonRecord) {
  const data = view.data;
  return isRecord(data) && Array.isArray(data.values) ? data.values : [];
}

function categoryMetrics(view: JsonRecord) {
  const values = valuesFrom(view);
  const labels = values.map((value) => (isRecord(value) ? String(value.x ?? "") : ""));
  return {
    count: labels.length,
    maxLabelLength: Math.max(0, ...labels.map((label) => [...label].length)),
  };
}

function styleBar(view: JsonRecord, width: number) {
  const encoding = isRecord(view.encoding) ? { ...view.encoding } : {};
  const { count, maxLabelLength } = categoryMetrics(view);
  const horizontal = count > 8 || maxLabelLength > 14;

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
    mark: { type: "bar", cornerRadiusEnd: 3 },
    encoding,
  };
}

function styleView(view: JsonRecord, width: number): JsonRecord {
  const type = markType(view.mark);
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
