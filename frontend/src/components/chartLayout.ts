type JsonRecord = Record<string, unknown>;

const TAU = Math.PI * 2;
const DONUT_LABEL_FONT_SIZE = 11;
const DONUT_VALUE_RADIUS = 90;
const DONUT_COLOR_SCHEME = "tableau10";
const DONUT_LEGEND_ROW_HEIGHT = 20;
const DONUT_LEGEND_GAP = 26;
const DONUT_LEGEND_CATEGORY_WIDTH = 126;
const DONUT_LEGEND_VALUE_WIDTH = 72;

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

// 차트 높이 계산에 쓰는 범주(카테고리) 개수를 센다.
function categoryCount(view: JsonRecord) {
  const values = valuesFrom(view);
  const labels = new Set(values.map((value) => (isRecord(value) ? String(value.x ?? "") : "")));
  return labels.size;
}

// Vega-Lite의 ",.2~f"와 같은 형태로 레이블 폭 계산용 숫자 문자열을 만든다.
function formatDonutValue(value: number) {
  return new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(value);
}

// 캔버스 측정 전에도 안전하게 안쪽 배치 여부를 판단할 수 있도록 폭을 보수적으로 추정한다.
function estimateLabelWidth(text: string) {
  return text.length * 7;
}

// Vega의 0시 방향·시계 방향 극좌표를 화면 좌표로 변환한다.
function polarPoint(centerX: number, centerY: number, radius: number, theta: number) {
  return {
    x: centerX + Math.sin(theta) * radius,
    y: centerY - Math.cos(theta) * radius,
  };
}

// 실제 뷰 크기에서 조각 안에 안전하게 들어가는 숫자 레이블 위치를 계산한다.
function layoutDonutValues(values: unknown[], size: number) {
  const entries = values.map((datum, index) => {
    const record = isRecord(datum) ? datum : {};
    const numericValue = Number(record.value);
    const order = Number(record._order);
    return {
      index,
      record,
      value: Number.isFinite(numericValue) ? numericValue : 0,
      order: Number.isFinite(order) ? order : index,
      theta: 0,
      placement: "hidden",
    };
  });
  const ordered = [...entries].sort((a, b) => a.order - b.order);
  const positiveTotal = ordered.reduce((sum, entry) => sum + Math.max(entry.value, 0), 0);
  const outerRadius = clamp(Math.round(size * 0.39), 108, 164);
  const innerRadius = clamp(Math.round(outerRadius * 0.34), 38, 56);
  const insideRadius = DONUT_VALUE_RADIUS;
  let cumulative = 0;

  for (const entry of ordered) {
    if (entry.value <= 0 || positiveTotal <= 0) {
      continue;
    }
    const share = entry.value / positiveTotal;
    entry.theta = ((cumulative + entry.value / 2) / positiveTotal) * TAU;
    cumulative += entry.value;
    const availableArcLength = share * TAU * insideRadius;
    const requiredWidth = estimateLabelWidth(formatDonutValue(entry.value)) + 10;
    entry.placement = availableArcLength >= requiredWidth ? "inside" : "hidden";
  }

  const legendHeight = Math.max((ordered.length - 1) * DONUT_LEGEND_ROW_HEIGHT, 0);
  const height = Math.max(size, legendHeight + 32);
  const centerX = size / 2;
  const centerY = height / 2;
  const legendStartY = centerY - legendHeight / 2;
  const legendRowByIndex = new Map(
    ordered.map((entry, row) => [entry.index, legendStartY + row * DONUT_LEGEND_ROW_HEIGHT]),
  );
  const legendSymbolX = size + DONUT_LEGEND_GAP;
  const legendCategoryX = legendSymbolX + 14;
  const legendValueX = legendCategoryX
    + DONUT_LEGEND_CATEGORY_WIDTH
    + DONUT_LEGEND_VALUE_WIDTH;

  const laidOutValues = entries.map((entry) => {
    const inside = polarPoint(centerX, centerY, insideRadius, entry.theta);
    const legendLabel = typeof entry.record._legend_label === "string"
      ? entry.record._legend_label
      : `${String(entry.record.x ?? "")}  ${formatDonutValue(entry.value)}`;
    return {
      ...entry.record,
      _labelPlacement: entry.placement,
      _labelX: inside.x,
      _labelY: inside.y,
      _legend_label: legendLabel,
      _legendY: legendRowByIndex.get(entry.index) ?? centerY,
    };
  });
  const legendDomain = ordered.map((entry) => {
    const record = laidOutValues[entry.index];
    return String(record._legend_label);
  });

  return {
    values: laidOutValues,
    width: size,
    height,
    innerRadius,
    outerRadius,
    legendDomain,
    legendSymbolX,
    legendCategoryX,
    legendValueX,
  };
}

function quantitativePosition(field: string) {
  return { field, type: "quantitative", scale: null };
}

function donutTextLayer(): JsonRecord {
  return {
    transform: [{ filter: "datum._labelPlacement === 'inside'" }],
    mark: {
      type: "text",
      fontSize: DONUT_LABEL_FONT_SIZE,
      baseline: "middle",
      align: "center",
    },
    encoding: {
      x: quantitativePosition("_labelX"),
      y: quantitativePosition("_labelY"),
      text: { field: "value", type: "quantitative", format: ",.2~f" },
      color: { value: "#111827" },
    },
  };
}

function donutLegendColor(domain: string[]) {
  return {
    field: "_legend_label",
    type: "nominal",
    scale: { scheme: DONUT_COLOR_SCHEME, domain },
    legend: null,
  };
}

function donutLegendLayers(
  domain: string[],
  symbolX: number,
  categoryX: number,
  valueX: number,
): JsonRecord[] {
  return [
    {
      mark: {
        type: "text",
        text: "●",
        fontSize: 14,
        baseline: "middle",
        align: "center",
      },
      encoding: {
        x: { value: symbolX },
        y: quantitativePosition("_legendY"),
        color: donutLegendColor(domain),
      },
    },
    {
      mark: {
        type: "text",
        align: "left",
        baseline: "middle",
        fontSize: 11,
        limit: DONUT_LEGEND_CATEGORY_WIDTH,
      },
      encoding: {
        x: { value: categoryX },
        y: quantitativePosition("_legendY"),
        text: { field: "x", type: "nominal" },
        color: { value: "#344054" },
      },
    },
    {
      mark: {
        type: "text",
        align: "right",
        baseline: "middle",
        fontSize: 11,
        fontWeight: 600,
      },
      encoding: {
        x: { value: valueX },
        y: quantitativePosition("_legendY"),
        text: { field: "value", type: "quantitative", format: ",.2~f" },
        color: { value: "#344054" },
      },
    },
  ];
}

// 넓은 조각만 내부에 표시하고, 모든 값은 겹치지 않는 범례에서 확인할 수 있게 한다.
function styleDonut(view: JsonRecord, size: number): JsonRecord {
  const layers = Array.isArray(view.layer) ? view.layer.filter(isRecord) : [];
  const arcLayer = layers.find((layer) => markType(layer.mark) === "arc");
  const values = valuesFrom(view);
  if (!arcLayer || values.length === 0) {
    return { ...view, width: size, height: size };
  }

  const layout = layoutDonutValues(values, size);
  const arcMark: JsonRecord = isRecord(arcLayer.mark)
    ? { ...arcLayer.mark }
    : { type: "arc" };
  arcMark.innerRadius = layout.innerRadius;
  arcMark.outerRadius = layout.outerRadius;
  const inheritedEncoding = isRecord(view.encoding) ? view.encoding : {};
  const layerEncoding = isRecord(arcLayer.encoding) ? arcLayer.encoding : {};
  const arcEncoding = { ...inheritedEncoding, ...layerEncoding };
  const sourceColor = isRecord(arcEncoding.color) ? arcEncoding.color : {};
  arcEncoding.color = {
    ...sourceColor,
    field: "_legend_label",
    type: "nominal",
    title: "",
    scale: { scheme: DONUT_COLOR_SCHEME, domain: layout.legendDomain },
    legend: null,
  };

  const styled: JsonRecord = {
    ...view,
    width: layout.width,
    height: layout.height,
    data: { values: layout.values },
    layer: [
      { ...arcLayer, mark: arcMark, encoding: arcEncoding },
      donutTextLayer(),
      ...donutLegendLayers(
        layout.legendDomain,
        layout.legendSymbolX,
        layout.legendCategoryX,
        layout.legendValueX,
      ),
    ],
  };
  delete styled.encoding;
  return styled;
}

// 서버가 정한 방향(기본 세로형)을 그대로 존중하며 막대 크기·모서리만 조정한다.
function styleBar(view: JsonRecord, width: number) {
  const encoding = isRecord(view.encoding) ? { ...view.encoding } : {};
  const count = categoryCount(view);
  // 방향은 서버 encoding으로 판별한다(값 축이 x축이면 가로형). 여기서 방향을 바꾸지 않는다.
  const horizontal = isRecord(encoding.x) && (encoding.x as JsonRecord).field === "value";

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
    const size = clamp(Math.floor(width * 0.62), 280, 420);
    return styleDonut(view, size);
  }
  if (type === "rect") {
    const count = categoryCount(view);
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
