# -*- coding: utf-8 -*-

SEARCH_STATISTICS = "자연어 질의와 관련 있는 통계표를 검색한다."
SEARCH_TABLES = "통계표의 표 본문과 메타데이터를 가져온다."
VISUALIZE = (
    "통계표 데이터를 질의와 차트 파라미터에 맞춰 검증한 뒤 세 가지 형태로 반환한다: "
    "(1) 인라인 PNG 이미지(이미지 렌더 가능한 클라이언트용), "
    "(2) structuredContent.asset.image_url 의 HTTP 링크(클릭/임베드용), "
    "(3) structuredContent.vega_lite 의 표준 Vega-Lite spec(위젯 렌더 가능한 클라이언트용). "
    "클라이언트가 지원하는 형태를 골라 최종 답변에 사용한다. "
    "컨텍스트가 작은 모델은 include_image=false 로 인라인 이미지를 생략할 수 있다."
)
