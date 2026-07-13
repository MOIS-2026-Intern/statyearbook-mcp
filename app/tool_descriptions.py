# -*- coding: utf-8 -*-

SEARCH_STATISTICS = "자연어 질의와 관련 있는 통계표를 검색한다."
SEARCH_TABLES = "통계표의 표 본문과 메타데이터를 가져온다."
VISUALIZE = (
    "통계표 데이터를 질의와 차트 파라미터에 맞춰 검증하고 "
    "structuredContent.vega_lite에 프론트엔드가 직접 렌더링할 표준 Vega-Lite spec을 반환한다. "
    "사용자가 연도나 도시·지역을 특정하면 year와 city에 각각 추출해 전달하고, "
    "평탄화된 '상위 헤더_하위 헤더' 표에서 특정 상위 헤더를 요구하면 column_family에 전달한다. "
    "서버는 이 값을 실제 표의 행과 '_' 컬럼군에 대조하며, 일치하지 않으면 전체 데이터로 대체하지 않는다. "
    "total_mode는 auto(기본), include, exclude 중 하나이며 구성비 차트에서 집계 범주의 포함 여부를 제어한다."
)
