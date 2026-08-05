# -*- coding: utf-8 -*-

ANALYZE_PUBLICATIONS = (
    "통계연보 자체의 구성 요소와 메타데이터를 조회·집계한다. 통계 항목·표·장·절·담당 부서·담당자·"
    "출처·주석의 전체 목록, 개수와 분포에 사용한다. 질문에 이미 담당자·담당 부서·출처 값이 주어져 "
    "그 값에 연결된 통계표를 역검색할 때도 사용한다. 통계 주제를 찾거나 그 주제의 담당 정보를 묻는 "
    "요청에는 사용하지 않는다. 통계표 본문의 실제 수치에는 사용하지 않으며, 서로 다른 발간판 사이의 "
    "차이는 compare_publications를 사용한다. 세부 집계 방식과 필드는 각 인자 설명을 따른다."
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
        "footnotes=주석. "
        "organizations는 연보에 통계를 제공한 담당 부서일 뿐이므로, 통계표가 조사한 행정기관·"
        "지방자치단체·위원회의 수를 묻는 질문에는 어떤 subject도 쓰지 않고 search_statistics로 넘긴다."
    ),
    "group_by": (
        "breakdown 전용 그룹 기준. publication_year, chapter, section, organization, "
        "source_system 중 하나. overview/count/list에서는 생략한다."
    ),
    "distinct_field": (
        "count와 breakdown 전용. 레코드 수가 아니라 이 필드의 중복 없는 값이 몇 가지인지 센다. "
        "전화번호 개수는 subject=contacts와 distinct_field=phone, 담당자 수는 officer, "
        "출처 URL 수는 source_url처럼 지정한다. breakdown에서는 group_by로 묶인 그룹마다 "
        "값의 가짓수를 센다. 값이 비어 있는 행은 자동으로 제외한다. "
        "subject가 이미 값 단위인 organizations·source_systems나 레코드 자체를 세는 "
        "질문에서는 생략한다."
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
        "값이 비어 있는지만 판정하므로 특정 이름·부서로 좁히려면 value_filters를 쓴다. "
        "표시용 문맥 필드는 fields에만 넣고 required_fields에는 넣지 않는다."
    ),
    "value_filters": (
        "특정 값을 가진 레코드만 남기는 조건 목록으로 count·breakdown·list에서 쓴다. "
        "담당자 이름은 officer, 담당 부서는 department, 출처 시스템은 source_system, "
        "전화번호는 phone, 주석 내용은 note로 지정한다. subject=contacts는 department·officer·"
        "phone·source_system·source_url, footnotes는 note_no·note, organizations는 department, "
        "source_systems는 source_system만 조건으로 받는다. "
        "비교는 공백·가운뎃점·대소문자를 무시한 부분 일치이므로 '홍길동'으로 '주무관 홍길동'을 찾는다. "
        "여러 조건을 함께 주면 모두 만족하는 레코드만 남는다."
    ),
    "deduplicate": (
        "list 중복 처리. 값 자체의 목록을 겹치지 않게 보려면 true, 통계 항목마다 연결된 레코드를 "
        "빠짐없이 보려면 false. 전화번호·담당자처럼 여러 통계 항목이 같은 값을 공유하는 필드만 "
        "나열할 때는 true가 필요하다. 생략하면 contacts/footnotes/statistics/tables는 전체 "
        "레코드를 유지하고 장·절·담당 부서·출처 시스템·발간판 목록만 중복 제거한다."
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
VALUE_FILTER_FIELDS = {
    "field": (
        "값을 대조할 필드. 담당자는 officer, 담당 부서는 department, 출처 시스템은 source_system, "
        "전화번호는 phone, 출처 URL은 source_url, 주석은 note_no 또는 note를 쓴다."
    ),
    "contains": (
        "그 필드에 포함되어야 할 검색어. 직함이나 괄호 설명은 빼고 이름·부서명만 넣는다. "
        "예: '주무관 홍길동'을 찾을 때는 '홍길동'."
    ),
}


COMPARE_PUBLICATIONS = (
    "서로 다른 두 발간판(예: 2025년판과 2026년판)의 수록 항목을 맞대어, 한쪽에만 있는 항목, "
    "양쪽에 다 있는 항목, 양쪽에 있으나 값이 달라진 항목을 찾는다. "
    "'25년판에만 있고 26년판에는 없는 자료가 몇 개인지', '새로 생긴 통계', '없어진 통계', "
    "'담당 부서가 바뀐 통계'처럼 두 판을 비교해야 답할 수 있는 질문에 사용한다. "
    "한 발간판 안의 개수나 분포만 필요하면 analyze_publications를 사용한다. "
    "operation은 summary=다섯 가지 건수를 한 번에, only_in_base=base 발간판에만 있는 항목 목록, "
    "only_in_target=target 발간판에만 있는 항목 목록, in_both=양쪽 공통 항목을 base·target 값 쌍으로, "
    "changed=공통 항목 중 비교 필드 값이 달라진 항목이다. 건수를 물으면 먼저 summary를 부르고, "
    "'그게 뭔데'처럼 실제 항목을 물으면 only_in_base 또는 only_in_target으로 목록을 가져온다. "
    "발간판마다 목차 번호가 다시 매겨지므로 기본 대응 기준은 이름(match_by=title)이다. "
    "각 항목의 실제 표 수치나 내용까지 답해야 하면 결과의 stat_id로 search_tables를 호출한다. "
    "응답의 limitations와 record_count를 그대로 근거로 인용하고, 임의 SQL은 받지 않는다."
)
COMPARE_PUBLICATIONS_FIELDS = {
    "operation": (
        "비교 방식. summary=한쪽에만 있는 수·공통 수·변경 수와 양쪽 총계, "
        "only_in_base=base 발간판에만 있는 항목 목록, only_in_target=target 발간판에만 있는 항목 목록, "
        "in_both=양쪽 공통 항목을 base_/target_ 값 쌍으로, changed=공통 항목 중 값이 달라진 항목."
    ),
    "subject": (
        "비교 대상. statistics=논리 통계 항목, chapters=장, sections=절, "
        "organizations=contacts.dept 담당 부서, source_systems=출처 시스템. "
        "'자료', '통계', '표'를 묻는 질문은 statistics를 쓴다."
    ),
    "match_by": (
        "두 발간판에서 같은 항목으로 볼 기준. title=이름의 공백·기호 차이를 지운 값(기본값), "
        "title_and_unit=이름과 단위를 함께 비교해 이름이 같고 단위가 다른 항목을 나누며 statistics 전용, "
        "number=목차 번호(statistics는 ref_id, chapters·sections는 장·절 번호). "
        "목차 번호는 발간판마다 다시 매겨지므로 number는 사용자가 번호 기준을 요구할 때만 쓴다. "
        "organizations와 source_systems는 title만 지원한다."
    ),
    "base_publication_year": (
        "비교 기준이 되는 발간연도. '25년판에만 있고 26년판에 없는 자료'라면 2025다. "
        "표 안 데이터 연도가 아니다. 두 연도를 모두 생략하면 가장 최근 두 발간판을 비교한다."
    ),
    "target_publication_year": (
        "맞대어 볼 발간연도. '25년판에만 있고 26년판에 없는 자료'라면 2026이다. "
        "생략하면 base 다음으로 가까운 최신 발간판을 적용한다."
    ),
    "fields": (
        "반환할 항목 필드이자 changed의 변경 판정 대상. statistics는 stat_id/ref_id/장·절·제목·"
        "단위·기준일·시작 페이지, chapters는 chapter_no/chapter, sections는 chapter_no/section_no/"
        "section, organizations는 organization, source_systems는 source_system을 쓸 수 있다. "
        "생략하면 subject별 기본 필드를 반환한다. 항목의 표 내용을 이어서 조회하려면 stat_id를 포함한다. "
        "stat_id와 page_start는 발간판마다 새로 부여되므로 변경 판정에서 제외된다."
    ),
    "limit": (
        "목록 operation이 반환할 최대 행 수로 1~500. truncated=true이면 next_offset으로 "
        "다음 목록을 조회한다. summary에는 영향이 없다."
    ),
    "offset": "목록 페이지 시작 위치. 첫 조회는 0이며 다음 조회는 반환된 next_offset을 사용한다.",
}


SEARCH_CONTACTS = (
    "stat_id로 특정 통계표의 담당 부서·담당자·전화번호와 출처를 조회한다. 자연어 통계 주제의 담당 "
    "정보를 묻는 경우 먼저 search_statistics로 stat_id를 찾는다. 질문에 이미 주어진 담당자나 부서를 "
    "기준으로 통계표를 역검색하는 요청에는 analyze_publications를 사용한다."
)
SEARCH_CONTACTS_FIELDS = {
    "stat_id": "search_statistics 등에서 확인한 통계표 식별자.",
}


SEARCH_STATISTICS = (
    "통계표의 제목 계층, 컬럼과 행 항목을 자연어로 검색해 후보와 stat_id를 반환한다. 선택한 통계표의 "
    "담당 정보가 필요하면 이어서 search_contacts를, 실제 표 수치나 원문이 필요하면 search_tables를 "
    "사용한다. publication_year는 통계연보 발간연도이며, 생략하면 통계마다 가장 최근 발간판을 검색한다."
)
SEARCH_STATISTICS_FIELDS = {
    "query": (
        "찾을 통계표의 제목, 컬럼명 또는 행·분류 항목 핵심어. 요청할 정보, 데이터 연도와 "
        "작업 표현은 제외하고 표를 식별하는 말만 전달한다. "
        "예: '행정기관 위원회', '사망신고 건수'"
    ),
    "publication_year": (
        "통계연보의 발간연도 또는 판 연도. 데이터 행의 연도나 기준연도가 아니다. "
        "'2025년 연보', '2025년판'처럼 발간판을 명시한 경우에만 전달하며, "
        "생략하면 통계별로 가장 최근 발간판을 사용한다."
    ),
    "limit": "반환할 통계표 후보의 최대 개수.",
}
SEARCH_TABLES = (
    "stat_id에 해당하는 통계표 원문(table_md), 제목 계층, 주석, 담당 부서·담당자·전화번호와 출처를 가져온다. "
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
