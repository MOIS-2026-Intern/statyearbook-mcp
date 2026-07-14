# -*- coding: utf-8 -*-

SEARCH_STATISTICS = (
    "통계표 제목 후보를 검색한다. publication_year는 통계연보의 발간판 연도이며 "
    "표 안의 데이터 연도나 기준연도가 아니다. 일반적인 '2024년 통계' 질문에서는 "
    "publication_year를 생략하고, 검색한 표 본문에서 2024년 행을 찾아야 한다. "
    "발간연도 필터로 결과가 없으면 필터를 자동으로 완화해 후보를 반환한다."
)
SEARCH_STATISTICS_FIELDS = {
    "query": (
        "찾을 통계표의 핵심 주제어. 연도와 '시각화', '그래프', '보여줘' 같은 작업 표현은 "
        "가능하면 제외한다. 예: '행정기관 위원회'"
    ),
    "publication_year": (
        "통계연보의 발간연도 또는 판 연도. 데이터 행의 연도나 기준연도가 아니다. "
        "'2025년 연보', '2025년판'처럼 발간판을 명시한 경우에만 전달한다."
    ),
    "limit": "반환할 통계표 후보의 최대 개수.",
}
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
SELECTION_FILTER_FIELDS = {
    "column": "search_tables 표에 나온 정확한 필터 컬럼명",
    "value": "search_tables 표에 나온 정확한 셀 값",
}
METRIC_SELECTION_FIELDS = {
    "column": "search_tables 표에 나온 정확한 숫자 컬럼명",
    "label": "차트에 표시할 짧은 지표명",
    "unit": "표 메타데이터와 일치하는 지표 단위",
}
VISUALIZE_FIELDS = {
    "table_handle": "직전 search_tables가 해당 표에 발급한 캐시 핸들",
    "x": "실제 x축 컬럼명 또는 연도·분류 같은 역할",
    "y": "실제 y축 숫자 컬럼명 또는 값·정원 같은 역할",
    "year": "사용자가 특정한 데이터 행의 연도. 날짜가 있으면 연도 정수만 추출",
    "city": "사용자가 특정한 도시·시도·지역명. 표의 실제 행 값과 서버에서 대조",
    "column_family": "'상위 헤더_하위 헤더'로 평탄화된 컬럼 중 요청한 상위 헤더명",
    "filters": "원본 행을 고르는 정확한 컬럼-값 조건. search_tables 값을 그대로 사용",
    "metrics": "시각화할 정확한 숫자 컬럼 목록. 여러 지표 비교 시 모두 전달",
}
