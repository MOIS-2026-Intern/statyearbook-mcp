# -*- coding: utf-8 -*-

ANALYZE_PUBLICATIONS = (
    "통계연보 한 발간판 또는 여러 발간판의 모든 통계 항목을 대상으로 기초통계를 집계하거나 "
    "공통 메타데이터·연락처·출처·주석 목록을 조회한다. 개별 통계표 본문 속 수치 검색이 아니라 "
    "연보 전체 건수, 계층 수, 기관·출처 수, 그룹별 분포 또는 전체 통계표에 걸친 정보 목록 요청에 "
    "사용한다. operation은 다음 SQL 템플릿을 고른다: "
    "overview는 한 번에 발간판 메타데이터와 주요 개수를 반환하고, count는 subject 하나의 "
    "정확한 개수를 반환하며, breakdown은 subject를 group_by 기준으로 묶고, list는 subject의 "
    "요청 필드 목록을 지정된 중복 처리 방식으로 반환한다. "
    "subject=statistics는 statistics.stat_id 기준 논리 통계 항목, tables는 stat_tables.table_id "
    "기준 물리 표 레코드, chapters/sections는 번호 계층, organizations는 contacts.dept에 파싱된 "
    "담당 부서, source_systems는 contacts.source_system, publications는 publications.pub_id, "
    "contacts는 모든 통계 항목의 담당 부서·담당자·전화번호·출처, footnotes는 주석을 뜻한다. "
    "list에서는 사용자가 요구한 값과 이를 설명할 문맥만 fields에 넣고, 반드시 값이 있어야 하는 "
    "핵심 필드는 required_fields에 넣는다. contacts와 footnotes는 기본적으로 각 레코드를 모두 "
    "유지하며, 사용자가 고유값·중복 제거를 명시한 경우에만 deduplicate=true를 사용한다. "
    "전체 통계표별 연락처를 구분해야 하면 statistic_title 또는 stat_id를 fields에 포함한다. "
    "발간연도를 생략하면 최신 발간판을 적용한다. 여러 연도 전체가 필요할 때만 "
    "all_publication_years=true를 사용한다. 임의 SQL은 받지 않으며 허용된 SELECT·JOIN·WHERE·GROUP BY "
    "조각과 필드만 조합한다. organizations는 공식 제출기관 테이블이 아니라 출처 문단의 담당 부서 기준이다."
)
ANALYZE_PUBLICATIONS_FIELDS = {
    "operation": (
        "SQL 템플릿. overview=주요 기초통계 묶음, count=subject 단일 개수, "
        "breakdown=group_by별 subject 개수, list=연보 전체에서 subject의 필드 목록 조회."
    ),
    "subject": (
        "집계 대상. statistics=논리 통계 항목(stat_id), tables=물리 표 레코드(table_id), "
        "chapters=장, sections=절, organizations=contacts.dept 담당 부서, "
        "source_systems=출처 시스템, publications=발간판, contacts=담당 부서·담당자·전화번호·출처, "
        "footnotes=주석."
    ),
    "group_by": (
        "breakdown 전용 그룹 기준. publication_year, chapter, section, organization, "
        "source_system 중 하나. overview/count/list에서는 생략한다."
    ),
    "fields": (
        "list 전용 반환 필드. subject에 맞는 필드 중 사용자가 요구한 것만 선택한다. "
        "발간판은 publication_year/publication_title/publication_page_count, 통계 항목은 "
        "stat_id/ref_id/장·절·제목·단위·기준일·시작 페이지, 물리 표는 table_id/table_seq/"
        "table_caption/row_count/column_count, 연락처·출처는 department/officer/phone/"
        "source_system/source_url, 주석은 note_seq/note_no/note를 사용할 수 있다. "
        "생략하면 subject별 기본 상세 필드를 반환한다."
    ),
    "required_fields": (
        "list 전용 필수값 필드. fields 중 실제 요청의 핵심값으로, 값이 비어 있는 행을 제외할 때 사용한다. "
        "전화번호 요청은 phone, 담당자 요청은 officer, URL 요청은 source_url처럼 지정한다. "
        "표시용 문맥 필드는 fields에만 넣고 required_fields에는 넣지 않는다."
    ),
    "deduplicate": (
        "list 중복 처리. 고유값·중복 제거 요청은 true, 전체 통계 항목에 연결된 레코드를 빠짐없이 "
        "보는 요청은 false. 생략하면 contacts/footnotes/statistics/tables는 전체 레코드를 유지하고 "
        "장·절·담당 부서·출처 시스템·발간판 목록만 중복 제거한다."
    ),
    "publication_year": (
        "통계연보 발간연도. 표 안 데이터 연도가 아니다. 생략하면 최신 발간연도를 적용한다."
    ),
    "all_publication_years": (
        "모든 발간판을 대상으로 비교·집계할 때만 true. publication_year와 동시에 사용하지 않는다."
    ),
    "chapter_no": "특정 장만 집계하는 선택 필터.",
    "section_no": "특정 절 번호만 집계하는 선택 필터. 장 번호와 함께 쓰면 한 절로 좁혀진다.",
    "limit": (
        "breakdown 또는 list가 반환할 최대 행 수로 1~500. '모두' 요청에는 500을 사용하고, "
        "truncated=true이면 next_offset으로 다음 목록을 조회한다. overview/count에는 영향이 없다."
    ),
    "offset": "list 페이지 시작 위치. 첫 조회는 0이며 다음 조회는 반환된 next_offset을 사용한다.",
}


SEARCH_STATISTICS = (
    "제목 계층, 표 컬럼명과 숫자가 아닌 행·분류 항목을 함께 사용해 통계표 후보와 stat_id를 검색한다. "
    "level3_title은 상위 통계 주제이고 level4_title/title_ko는 실제 표 제목이다. "
    "table_seq는 검색어가 발견된 원자료 표 순번이고 matched_source/matched_text는 "
    "제목·컬럼·행 항목 중 실제 검색 근거를 나타낸다. "
    "이 도구의 결과는 후보 메타데이터이므로 "
    "통계 수치를 답할 때는 선택한 stat_id로 search_tables를 호출해 표 본문을 확인한다. "
    "publication_year는 통계연보의 발간판 연도이며 표 안의 데이터 연도나 기준연도가 아니다. "
    "publication_year를 생략하면 가장 최근 발간판을 자동으로 적용한다. "
    "일반적인 '2024년 통계' 질문의 2024년은 데이터 연도이므로 publication_year로 전달하지 않는다. "
    "발간연도 필터로 결과가 없으면 도구가 필터를 자동으로 완화한다."
)
SEARCH_STATISTICS_FIELDS = {
    "query": (
        "찾을 통계표의 제목, 컬럼명 또는 행·분류 항목 핵심어. 데이터 연도와 '시각화', "
        "'그래프', '보여줘' 같은 작업 표현은 가능하면 제외한다. "
        "예: '행정기관 위원회', '사망신고 건수'"
    ),
    "publication_year": (
        "통계연보의 발간연도 또는 판 연도. 데이터 행의 연도나 기준연도가 아니다. "
        "'2025년 연보', '2025년판'처럼 발간판을 명시한 경우에만 전달하며, 생략하면 최신 발간판을 사용한다."
    ),
    "limit": "반환할 통계표 후보의 최대 개수.",
}
SEARCH_TABLES = (
    "stat_id에 해당하는 통계표 원문(table_md), 전체 제목 계층, 주석과 출처를 가져온다. "
    "한 제목의 표가 여러 페이지(seq)로 나뉘어 있으면 모두 합쳐 하나의 표로 제공하며, "
    "table_handle은 그 합쳐진 전체 표를 가리킨다. "
    "수치 단위는 반환된 unit을 기준으로 해석한다. 각 표의 table_handle은 같은 사용자 요청에서 "
    "visualize가 원본 표를 재조회하지 않고 재사용할 때만 쓴다."
    "행이 연도로 구분되어 있지만, 연도를 특정하지 않으면 가장 최신 연도를 기준으로 한 표를 반환한다."
)
VISUALIZE = (
    "통계표 데이터를 검증해 프론트엔드가 렌더링할 Vega-Lite spec을 반환한다. 가능하면 먼저 "
    "search_tables로 원본 표를 확인하고 같은 요청에서 받은 table_handle을 전달한다. 사용자가 요구한 행과 "
    "숫자 지표는 표의 정확한 컬럼명·셀 값으로 filters와 metrics에 전달하며, 비교할 지표가 여러 개면 모두 "
    "포함한다. 표에 없는 이름이나 값을 만들지 않으며 검증 실패 시 전체 데이터로 대체하지 않는다."
)
SELECTION_FILTER_FIELDS = {
    "column": "search_tables 표에 나온 정확한 필터 컬럼명",
    "value": "search_tables 표에 나온 정확한 셀 값",
}
METRIC_SELECTION_FIELDS = {
    "column": "search_tables 표에 나온 정확한 숫자 컬럼명",
    "label": "차트에 표시할 짧은 한글 지표명. 컬럼명의 영문명은 제외",
    "unit": "표 메타데이터에서 단위가 명확할 때만 전달하는 지표 단위",
}
VISUALIZE_FIELDS = {
    "table_handle": "직전 search_tables가 해당 표에 발급한 캐시 핸들",
    "title": (
        "차트와 표에 표시할 짧은 한글 제목. 원본 통계표 제목을 바꾸는 값이 아니며, "
        "선택한 연도·지역·지표가 드러나게 작성한다. 예: '2024년 행정기관 위원회 수(소속별)'"
    ),
    "x": "실제 x축 컬럼명 또는 연도·분류 같은 역할",
    "y": "실제 y축 숫자 컬럼명 또는 값·정원 같은 역할",
    "year": "사용자가 특정한 데이터 행의 연도. 날짜가 있으면 연도 정수만 추출",
    "city": "사용자가 특정한 도시·시도·지역명. 표의 실제 행 값과 서버에서 대조",
    "column_family": "'상위 헤더_하위 헤더'로 평탄화된 컬럼 중 요청한 상위 헤더명",
    "filters": "원본 행을 고르는 정확한 컬럼-값 조건. search_tables 값을 그대로 사용",
    "metrics": "시각화할 정확한 숫자 컬럼 목록. 여러 지표 비교 시 모두 전달",
    "top_n": (
        "표시할 상위 범주(막대) 수. 생략하면 기본 상위 20개(도넛 8개)만 표시한다. "
        "사용자가 전체 항목·모든 행을 요청하면 0을 전달해 범주 제한 없이 전부 표시한다."
    ),
    "orientation": (
        "막대그래프 방향. 기본은 세로 막대(vertical)이며, 사용자가 가로 막대를 "
        "명시적으로 요청할 때만 horizontal을 전달한다."
    ),
    "sort_order": (
        "값을 기준으로 범주를 정렬할 방향. 사용자가 큰 값·많은 순·내림차순을 요청하면 "
        "descending, 작은 값·적은 순·오름차순을 요청하면 ascending을 전달한다. "
        "값 기준 정렬 요청이 없으면 auto를 전달한다."
    ),
    "total_mode": (
        "구성비·비율 차트의 합계 범주 처리. 합계 포함 요청은 include, 제외 요청은 exclude, "
        "불명확하면 auto"
    ),
}
