# -*- coding: utf-8 -*-

ANALYZE_PUBLICATIONS = (
    "연보라는 책에 무엇이 어떻게 수록되어 있는지를 조회한다. 몇 개의 통계 항목·표·장·절이 실렸고 "
    "어떤 담당 부서·담당자·출처·주석이 붙어 있는지가 대상이며, 표 안에 적힌 수치는 다루지 않는다. "
    "중앙행정기관·지방자치단체·위원회·공무원처럼 통계표가 조사한 실제 대상이 몇 개인지 묻는 질문은 "
    "'총 몇 개'라고 물어도 이 도구의 대상이 아니라 search_statistics로 표를 찾아 답한다. "
    "질문에 담당자 이름이나 담당 부서명이 주어져 그 담당자가 맡은 통계를 역검색할 때도 사용한다. "
    "이때는 subject=contacts에 value_filters로 officer 또는 department 조건을 걸고, 담당 통계 "
    "목록을 답하려면 fields에 ref_id와 statistic_title을 함께 넣는다. 담당자 이름은 표 제목이나 "
    "본문에 없어 search_statistics로는 찾지 못한다. "
    "반대로 통계 주제를 찾는 요청은 search_statistics, 특정 통계의 담당 정보는 search_contacts, "
    "표 본문의 수치는 search_tables, 발간판 사이의 차이는 compare_publications를 사용한다. "
    "세부 집계 방식과 필드는 각 인자 설명을 따른다."
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
        "organizations는 연보에 통계를 제출한 과·팀 이름의 종류일 뿐 부·처·청 같은 기관의 수가 "
        "아니다. 중앙행정기관·행정기관·지방자치단체·위원회가 몇 개인지 묻는 질문에는 어떤 subject도 "
        "쓰지 않고 search_statistics로 넘긴다."
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
        "ref_id/장·절·제목·단위·기준일·시작 페이지, 물리 표는 table_id/table_seq/"
        "table_caption/row_count/column_count, 연락처·출처는 department/officer/phone/"
        "source_system/source_url, 주석은 note_seq/note_no/note를 사용할 수 있다. "
        "연락처·주석 목록에서 어느 통계의 것인지 밝혀야 하면 ref_id와 statistic_title을 함께 넣는다. "
        "stat_id는 이어서 search_tables를 호출할 때만 넣고 답변에는 쓰지 않는다. "
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
        "source_systems는 source_system만 조건으로 받고 나머지 subject는 조건을 받지 않는다. "
        "담당자·담당 부서로 통계를 좁히려면 subject=contacts를 쓴다. "
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
    "publication_kind": (
        "조회할 발간물 종류. 통계연보는 yearbook, 주요통계집은 major_statistics를 사용한다. "
        "사용자가 주요통계집을 명시하지 않으면 yearbook을 기본값으로 둔다."
    ),
    "publication_period": (
        "조회할 발간 반기. 주요통계집만 같은 해에 상반기(H1)와 하반기(H2) 두 판이 나온다. "
        "사용자가 반기를 말한 경우에만 전달하고, 말하지 않으면 생략해 그 해의 모든 판을 본다. "
        "통계연보에는 반기가 없으므로 전달하지 않는다."
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
    "'담당 부서가 바뀐 통계'는 subject=statistics에 operation=changed와 "
    "fields=[ref_id, statistic_title, organization], compare_fields=[organization]으로 한 번에 묻는다. "
    "'담당자명이 바뀐 통계'는 fields=[ref_id, statistic_title, officer], "
    "compare_fields=[officer]로 묻는다. "
    "두 발간판의 담당 정보 목록을 "
    "각각 받아 직접 맞대어 보지 않는다. "
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
        "'자료', '통계', '표'를 묻는 질문은 statistics를 쓴다. "
        "organizations와 source_systems는 부서·시스템 자체가 새로 생기거나 없어졌는지를 보며, "
        "'어느 통계의 담당이 바뀌었는지'는 statistics에 organization 또는 officer를 넣어 묻는다."
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
        "표 안 데이터 연도가 아니다. 두 연도를 모두 생략하면 가장 최근 두 발간판을 비교한다. "
        "주요통계집에서 같은 해의 두 반기를 비교하려면 두 연도를 같게 두고 반기를 다르게 준다."
    ),
    "publication_kind": (
        "비교할 발간물 종류. 통계연보끼리 비교하면 yearbook, 주요통계집끼리 비교하면 "
        "major_statistics를 사용한다."
    ),
    "base_publication_period": (
        "base 발간판의 반기. 주요통계집은 같은 해에 상반기(H1)와 하반기(H2)가 모두 있어 "
        "그 해를 지정하면 반기도 함께 주어야 판이 하나로 정해진다. "
        "'25년 상반기와 하반기를 비교'하려면 base에 H1, target에 H2를 전달한다. "
        "통계연보에는 반기가 없으므로 전달하지 않는다."
    ),
    "target_publication_period": (
        "맞대어 볼 발간판의 반기. 값의 뜻은 base_publication_period와 같다."
    ),
    "target_publication_year": (
        "맞대어 볼 발간연도. '25년판에만 있고 26년판에 없는 자료'라면 2026이다. "
        "생략하면 base 다음으로 가까운 최신 발간판을 적용한다."
    ),
    "fields": (
        "응답에 반환할 항목 필드. compare_fields를 생략한 기존 호출에서는 changed의 변경 판정 "
        "대상도 겸한다. statistics는 stat_id/ref_id/장·절·제목·단위·기준일·시작 페이지와 "
        "organization(담당 부서)·officer(contacts.officer 담당자)·source_system(출처 시스템), "
        "chapters는 chapter_no/chapter, sections는 chapter_no/section_no/"
        "section, organizations는 organization, source_systems는 source_system을 쓸 수 있다. "
        "생략하면 subject별 기본 필드를 반환한다. 항목의 표 내용을 이어서 조회하려면 stat_id를 포함한다. "
        "stat_id와 page_start는 발간판마다 새로 부여되므로 변경 판정에서 제외된다. "
        "statistics를 match_by=title로 목록 비교할 때도 양쪽 목차 번호를 함께 보여주도록 ref_id를 포함한다. "
        "반환할 제목·식별자와 변경 판정 필드를 분리하려면 compare_fields를 함께 지정한다."
    ),
    "compare_fields": (
        "summary의 changed_count와 changed/in_both의 changed_fields를 판정할 필드. 생략하면 "
        "기존처럼 fields 중 비교 가능한 필드를 모두 사용한다. 담당 부서 변경만 찾을 때는 "
        "[organization], 담당자 변경만 찾을 때는 [officer]를 쓴다. officer는 contacts.officer "
        "값을 직접 비교하므로 이름이나 직급 어느 쪽이 달라져도 변경이다. stat_id와 page_start는 "
        "비교할 수 없다."
    ),
    "limit": (
        "목록 operation이 반환할 최대 행 수로 1~500. truncated=true이면 next_offset으로 "
        "다음 목록을 조회한다. summary에는 영향이 없다."
    ),
    "offset": "목록 페이지 시작 위치. 첫 조회는 0이며 다음 조회는 반환된 next_offset을 사용한다.",
}


SEARCH_CONTACTS = (
    "stat_id로 특정 통계표 하나의 담당 부서·담당자·전화번호와 출처를 조회한다. 통계 주제만 아는 "
    "경우 먼저 search_statistics로 stat_id를 찾는다. 반대로 담당자 이름이나 부서명이 주어져 그 "
    "담당자가 맡은 통계를 역검색하는 요청에는 analyze_publications를 사용한다."
)
SEARCH_CONTACTS_FIELDS = {
    "stat_id": "search_statistics 등에서 확인한 통계표 식별자.",
}


SEARCH_STATISTICS = (
    "통계표의 제목 계층, 컬럼과 행 항목, 표에 달린 주석을 자연어로 검색해 후보와 stat_id를 반환한다. "
    "통계 주제로 표를 찾는 첫 단계이며, 선택한 통계표의 담당 정보가 필요하면 이어서 search_contacts를, "
    "실제 표 수치나 원문이 필요하면 search_tables를 사용한다. "
    "중앙행정기관·지방자치단체·위원회·공무원처럼 통계표가 조사한 실제 대상의 수와 현황을 묻는 "
    "질문도 여기서 표를 찾은 뒤 search_tables로 수치를 읽어 답한다. "
    "사람 이름과 부서명은 표 제목이나 본문에 없으므로 query에 넣지 않고 analyze_publications를 쓴다. "
    "결과의 has_tables가 false인 후보는 조직도·도표처럼 표 본문이 없어 search_tables로 수치를 읽을 수 "
    "없으므로, 수치를 묻는 질문이면 has_tables가 true인 후보를 고른다. "
    "publication_year는 통계연보 발간연도이며, 생략하면 통계마다 가장 최근 발간판을 검색한다."
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
    "publication_kind": (
        "검색할 발간물 종류. 통계연보는 yearbook, 주요통계집은 major_statistics다. "
        "사용자가 주요통계집을 말한 경우 반드시 major_statistics를 전달한다."
    ),
    "publication_period": (
        "검색할 발간 반기. 주요통계집만 같은 해에 상반기(H1)와 하반기(H2) 두 판이 나온다. "
        "'2025년 하반기 주요통계집'처럼 반기를 밝힌 경우에만 전달하고, 밝히지 않으면 생략해 "
        "두 반기를 모두 검색한다. 통계연보에는 반기가 없으므로 전달하지 않는다. "
        "결과의 publication_period가 그 후보가 실린 실제 반기다."
    ),
    "limit": "반환할 통계표 후보의 최대 개수.",
}
SEARCH_TABLES = (
    "stat_id에 해당하는 통계표 원문(table_md), 제목 계층, 주석, 담당 부서·담당자·전화번호와 출처를 가져온다. "
    "표 안의 실제 수치를 확인하는 도구이며, stat_id를 모르면 먼저 search_statistics로 찾는다. "
    "한 제목의 표가 여러 페이지(seq)로 나뉘어 있으면 모두 합쳐 하나의 표로 제공하며, "
    "table_handle은 그 합쳐진 전체 표를 가리킨다. "
    "특정 지역·연도·구분 행의 값이 필요하면 row_label에 search_statistics의 matched_text나 "
    "사용자가 말한 행 라벨을 넣는다. row_label을 넣으면 table_md 미리보기 밖의 행도 "
    "matched_rows와 matched_rows_md로 별도 반환된다. "
    "특정 물리 표만 조회해야 할 때만 table_seq를 넣고, 보통은 생략한다. "
    "수치 단위는 반환된 unit을 기준으로 해석한다. 각 표의 table_handle은 같은 사용자 요청에서 "
    "visualize가 원본 표를 재조회하지 않고 재사용할 때만 쓴다. "
    "행이 연도로 구분되어 있지만, 연도를 특정하지 않으면 가장 최신 연도를 기준으로 한 표를 반환한다."
    "상관계수·평균·증감률처럼 표 수치를 가공해야 답이 나오는 요청은 이 도구로 필요한 표를 모두 "
    "확인한 뒤 그 값으로 직접 계산해 답한다. 통계량을 산출해 주는 도구는 따로 없다."
)
VISUALIZE = (
    "통계표 데이터를 검증해 프론트엔드가 렌더링할 Vega-Lite spec을 반환한다. 가능하면 먼저 "
    "search_tables로 원본 표를 확인하고 같은 요청에서 받은 table_handle을 전달한다. 사용자가 요구한 행과 "
    "숫자 지표는 표의 컬럼명·셀 값으로 filters와 metrics에 전달하며, 비교할 지표가 여러 개면 모두 "
    "포함한다. 표에 없는 이름이나 값을 만들지 않으며 검증 실패 시 전체 데이터로 대체하지 않는다. "
    "사용자가 표의 일부만 그려 달라고 하면 표 전체를 넘기지 말고 그릴 행은 filters로, 그릴 열은 "
    "metrics 또는 column_family로 좁힌다. 예를 들어 '공무원 정원을 급수별로'는 1급~9급 행만 남겨 "
    "경찰직·교육직을 빼고, '성별 말고 연령대별로'는 연령대 컬럼만 남긴다. "
    "한 표 안의 지표만 그릴 때는 stat_id로 호출하고, 서로 다른 표의 지표를 한 그래프에 놓아야 하면 "
    "표마다 search_statistics·search_tables로 확인한 뒤 sources에 표별 항목을 모두 담아 한 번만 호출한다. "
    "'A와 B를 함께/한 그래프에', 'A와 B의 관계를 그려줘', 'A 대비 B를 그려줘'처럼 서로 다른 주제를 "
    "그림 하나로 잇는 요청이 여기에 해당하며, 서버가 두 표에 공통으로 있는 지역·연도 항목을 맞춰 "
    "하나의 차트로 만든다. "
    "이 도구는 그림을 만들 때만 쓴다. '상관관계를 계산해줘', '상관계수를 알려줘'처럼 그림 없이 "
    "수치만 요구한 요청에는 호출하지 않고, search_tables로 표를 확인해 그 값으로 직접 계산해 답한다. "
    "이 도구는 상관계수·회귀선을 산출하지도, 차트에 그리지도 않는다. "
    "'주민 1만 명당 공무원 정원', '1인당 지방세', '인구 대비 채무 비율', '세대당 인구', '성비'처럼 "
    "나눈 값을 항목마다 차트로 그려야 하는 요청은 직접 계산하지 말고 derive로 계산 방법만 지정한다. 나눌 두 값이 "
    "서로 다른 표에 있으면 sources에 분자 표와 분모 표를 담고, 한 표 안의 두 컬럼이면 stat_id와 함께 "
    "metrics에 분자 컬럼과 분모 컬럼을 순서대로 담는다. 서버가 항목마다 나눠 값과 단위를 만들므로 "
    "계산 결과를 지어낼 필요가 없다."
)
SELECTION_FILTER_FIELDS = {
    "column": (
        "행을 고를 컬럼명. search_tables 표의 머리글을 쓰되 영문 병기와 띄어쓰기는 빼도 된다. 예: '구분'"
    ),
    "value": (
        "남길 행의 항목명. '1급 Grade 1'은 '1급'처럼 한국어 부분만 써도 되고 띄어쓰기 차이도 무시한다. "
        "여러 항목을 남기려면 같은 column으로 항목마다 하나씩 넣는다"
    ),
}
METRIC_SELECTION_FIELDS = {
    "column": (
        "search_tables 표에 나온 숫자 컬럼명. 영문 병기와 띄어쓰기는 빼도 되고, "
        "'상위헤더_하위헤더' 형태는 '연령별_20대'처럼 한국어만 남겨 써도 된다"
    ),
    "label": "차트에 표시할 짧은 한글 지표명. 컬럼명의 영문명은 제외",
    "unit": "표 메타데이터에서 단위가 명확할 때만 전달하는 지표 단위",
}
DERIVED_METRIC_FIELDS = {
    "op": (
        "두 표의 값을 항목마다 어떻게 계산할지. per_capita=분자÷분모×per로 '주민 1만 명당 정원'처럼 "
        "인구·세대 규모로 나눈 값, ratio=분자÷분모 배수, share=분자÷분모×100 백분율, "
        "difference=분자-분모 차이(두 표의 단위가 같아야 한다)"
    ),
    "numerator": (
        "분자로 쓸 값의 순번. 표를 둘 담았으면 sources 순번, 한 표 안의 두 컬럼이면 metrics 순번이다. "
        "첫 번째가 0이며 생략하면 0"
    ),
    "denominator": (
        "분모로 쓸 값의 순번. 표를 둘 담았으면 sources 순번, 한 표 안의 두 컬럼이면 metrics 순번이다. "
        "두 번째가 1이며 생략하면 1"
    ),
    "per": (
        "per_capita에서 분모에 곱할 기준 수량. '1만 명당'은 10000, '10만 명당'은 100000, "
        "'1인당'은 1을 전달한다. 사용자가 기준을 밝히지 않았으면 search_tables로 확인한 두 값의 "
        "크기를 견줘 읽기 좋은 기준을 직접 고른다. 분자가 분모보다 훨씬 작아 그냥 나누면 0.003처럼 "
        "1보다 작은 값이 나오는 경우(CCTV 대수당 관제인력, 인구당 공무원)에는 100·1000·10000 중 "
        "나눈 값이 한 자리 수 이상으로 읽히는 기준을 골라 전달한다. 나눈 값이 이미 1을 넘으면 "
        "1을 그대로 둔다. 생략하면 서버가 질의에 적힌 말에서 찾고, 그마저 없으면 값이 읽히는 "
        "기준으로 알아서 맞춘다"
    ),
    "label": (
        "차트 축과 제목에 쓸 짧은 한글 지표명. 예: '주민 1만 명당 지방공무원 정원'. "
        "생략하면 서버가 두 표 이름과 배수로 만든다"
    ),
}
SERIES_SOURCE_FIELDS = {
    "stat_id": "이 계열을 읽어 올 통계표의 stat_id",
    "table_handle": (
        "그 stat_id에 대해 이번 요청의 search_tables가 발급한 캐시 핸들. "
        "이전 요청에서 받은 핸들은 쓰지 않는다"
    ),
    "label": (
        "차트 범례와 축에 쓸 짧은 한글 계열명. 예: '주민등록인구', '지방자치단체 채무'. "
        "생략하면 통계표 제목을 사용한다"
    ),
    "key": (
        "표를 서로 맞출 기준 항목 컬럼명(지역·연도 등). 생략하면 서버가 표끼리 값이 가장 많이 "
        "겹치는 컬럼을 골라 대조한다"
    ),
    "value": (
        "그 표에서 그릴 정확한 숫자 컬럼명. 생략하면 서버가 표의 합계 성격 컬럼을 고르므로, "
        "특정 지표를 요구한 요청에는 search_tables에 나온 컬럼명을 그대로 전달한다"
    ),
    "unit": "그 계열의 단위. 표에 단위가 여러 개면 이 계열에 해당하는 단위만 전달",
    "year": "그 표에서 고를 데이터 행의 연도. 표마다 기준 연도가 다를 때만 전달",
    "filters": (
        "그 표에서 그릴 행만 남기는 컬럼-값 조건. 같은 컬럼을 여러 번 넣으면 그중 하나라도 "
        "맞는 행이 남는다"
    ),
}
VISUALIZE_FIELDS = {
    "stat_id": "한 표만 그릴 때 사용할 통계표 식별자. sources를 전달하면 생략한다",
    "sources": (
        "서로 다른 표의 지표를 한 그래프에 함께 그릴 때만 사용하는 표별 계열 목록. 2개 이상 5개 "
        "이하로 전달하며, 각 항목은 그 표의 stat_id와 그릴 숫자 컬럼(value)을 가리킨다. 서버가 "
        "표끼리 공통인 지역·연도 항목으로 값을 맞춰 하나의 차트로 만든다. 단위가 같으면 막대를 "
        "나란히 놓아 크기를 바로 견주게 하고, 단위가 다르면 값 축을 좌우로 나눠 막대와 선으로 "
        "겹친다. 두 지표의 관계를 묻는 요청은 chart_type='scatter'를 함께 전달하면 첫 항목이 "
        "x축, 두 번째 항목이 y축이 된다"
    ),
    "derive": (
        "두 값을 항목마다 나눠 새 지표 하나를 만들어 차트로 그릴 때만 전달한다. 'A당 B', '1인당', "
        "'1만 명당', '인구 대비', 'B 대비 A 비율', '세대당 인구'처럼 나눈 값을 항목마다 그려야 하는 "
        "요청이 여기에 해당하며, 차트 없이 수치만 묻는 요청에는 쓰지 않는다. "
        "사용자가 기준 수량을 밝히지 않았으면 per로 읽기 좋은 기준을 직접 정한다. 그냥 나누면 "
        "0.003처럼 1보다 작은 값이 되는 요청은 그대로 그리면 막대가 모두 0선에 붙어 아무것도 "
        "읽히지 않으므로, 값이 한 자리 수 이상이 되는 기준(100·1000 등)을 골라 전달한다. "
        "나눌 두 값이 서로 다른 표에 있으면 sources에 표를 두 개 담고, 한 표 안의 두 컬럼이면 "
        "metrics에 숫자 컬럼을 두 개 담아 함께 전달한다. 계산 방법만 지정하면 서버가 항목마다 "
        "계산하므로 표의 수치를 직접 나눠 값을 만들어 전달하지 않는다. 결과는 계열 하나짜리 차트가 "
        "되어 sort_order·top_n·orientation이 그대로 적용된다"
    ),
    "chart_type": (
        "그릴 차트 종류. 사용자가 차트를 지정하지 않았으면 auto를 전달해 서버가 질의 의도와 데이터 "
        "구조에 맞는 차트를 고르게 한다. 구조에 맞지 않는 차트를 전달하면 서버가 가장 가까운 차트로 "
        "바꾸고 그 이유를 warnings에 남긴다. "
        "각 값의 쓰임은 다음과 같다. "
        "bar=항목별 크기 비교, grouped_bar=단위가 같은 지표를 항목마다 나란히 비교, "
        "stacked_bar=항목별 합계와 그 구성을 함께, stacked_bar_100=합계 크기는 빼고 구성비만 비교, "
        "lollipop=항목이 많아 막대가 빽빽할 때의 크기 비교, "
        "diverging_bar=증감처럼 음수가 섞인 값을 0 기준으로 갈라 표시, "
        "waterfall=증감이 쌓여 마지막 값에 이르는 과정, "
        "line=시점별 추이, area=추이와 규모를 함께, slope=두 시점 사이 항목별 변화 방향, "
        "bump=시점별 순위 변화, "
        "combo=연도처럼 시간이 흐르는 축에서 단위가 다른 두 지표를 막대와 선으로 겹침. 선은 시간의 "
        "흐름을 나타내는 mark라 지역·기관처럼 순서 없는 항목 축에는 쓰지 않는다. 그런 축에서 단위나 "
        "규모가 다른 두 지표는 chart_type을 grouped_bar나 auto로 두면 서버가 지표마다 칸을 위아래로 "
        "나눠 각자의 값 축에 그린다, "
        "scatter=두 지표의 관계, dumbbell=단위가 같은 두 지표의 항목별 격차, "
        "heatmap=두 범주 축에 걸친 값의 분포, donut=한 시점의 구성비, table=차트 없이 표만"
    ),
    "table_handle": (
        "이번 요청에서 search_tables가 그 표에 발급한 캐시 핸들. 핸들은 요청이 끝나면 사라지므로 "
        "이전 요청에서 받은 값을 다시 쓰지 않고, 이번 요청에서 받지 않았으면 생략한다. "
        "표는 stat_id로도 읽으므로 stat_id는 언제나 함께 전달한다"
    ),
    "table_seq": (
        "쪽이 나뉜 표는 이미 하나로 합쳐져 있으므로 기본값 1을 그대로 둔다. "
        "search_tables 응답의 seq는 원문 쪽 번호일 뿐이며, 이 값을 바꿔도 다른 컬럼이 나오지 "
        "않는다. 원하는 컬럼이 없다는 경고가 나오면 seq를 바꿔 다시 부르지 말고 합쳐진 표에 "
        "실제로 있는 컬럼명을 쓴다."
    ),
    "title": (
        "차트와 표에 표시할 짧은 한글 제목. 원본 통계표 제목을 바꾸는 값이 아니며, "
        "선택한 연도·지역·지표가 드러나게 작성한다. 예: '2024년 행정기관 위원회 수(소속별)'"
    ),
    "x": "실제 x축 컬럼명 또는 연도·분류 같은 역할",
    "y": "실제 y축 숫자 컬럼명 또는 값·정원 같은 역할",
    "year": "사용자가 특정한 데이터 행의 연도. 날짜가 있으면 연도 정수만 추출",
    "city": "사용자가 특정한 도시·시도·지역명. 표의 실제 행 값과 서버에서 대조",
    "column_family": (
        "'상위 헤더_하위 헤더'로 평탄화된 컬럼 중 그릴 상위 헤더명. 그 헤더에 속한 하위 컬럼만 남는다. "
        "'성별은 빼고 연령대별로'처럼 한 상위 헤더 아래 컬럼만 필요할 때 '연령별'을 전달한다"
    ),
    "filters": (
        "그릴 행만 남기는 컬럼-값 조건. 사용자가 표의 일부 항목만 요청하면 그 항목을 빠짐없이 나열해 "
        "표 전체가 그려지지 않게 한다. 같은 컬럼을 여러 번 넣으면 그중 하나라도 맞는 행이 남고(OR), "
        "다른 컬럼끼리는 모두 맞아야 남는다(AND). 예를 들어 '공무원 정원을 급수별로'는 구분 컬럼에 "
        "1급부터 9급까지 아홉 조건을 넣어 경찰직·교육직 같은 나머지 행을 뺀다"
    ),
    "metrics": (
        "그릴 숫자 컬럼 목록. 표의 숫자 컬럼 중 사용자가 요청한 것만 넣어 열을 좁히며, "
        "여러 지표를 비교하는 요청에는 모두 전달한다. 한 상위 헤더 아래 컬럼을 통째로 쓸 때는 "
        "column_family가 더 간단하다"
    ),
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
