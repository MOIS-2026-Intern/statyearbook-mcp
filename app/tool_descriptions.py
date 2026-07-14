# -*- coding: utf-8 -*-

SEARCH_STATISTICS = "자연어 질의와 관련 있는 통계표를 검색한다."
SEARCH_TABLES = (
    "통계표의 표 본문과 메타데이터를 가져온다. 각 표의 table_handle은 같은 요청에서 "
    "visualize가 원본 표를 재조회하지 않고 재사용할 때 쓴다."
)
VISUALIZE = (
    "통계표 데이터를 질의와 차트 파라미터에 맞춰 검증하고 "
    "structuredContent.vega_lite에 프론트엔드가 직접 렌더링할 표준 Vega-Lite spec을 반환한다. "
    "search_tables를 먼저 호출했다면 해당 표의 table_handle을 전달한다. "
    "사용자가 요구한 행은 filters에 search_tables의 정확한 컬럼명과 셀 값으로, "
    "숫자 지표는 metrics에 정확한 컬럼명과 표시 라벨로 전달한다. 여러 지표는 모두 metrics에 넣는다. "
    "서버는 filters와 metrics를 원본 표에 엄격하게 대조하고 검증된 selected_dataset으로 표와 차트를 만든다. "
    "사용자가 연도나 도시·지역을 특정하면 year와 city에 각각 추출해 전달할 수도 있고, "
    "평탄화된 '상위 헤더_하위 헤더' 표에서 특정 상위 헤더를 요구하면 column_family에 전달한다. "
    "구조화된 선택 계획이 없을 때만 기존 질의 해석을 사용하며, 일치하지 않으면 전체 데이터로 대체하지 않는다. "
    "total_mode는 auto(기본), include, exclude 중 하나이며 구성비 차트에서 집계 범주의 포함 여부를 제어한다."
)
