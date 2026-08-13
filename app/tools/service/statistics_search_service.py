# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re

from app.query_embedding import (
    embed_query,
    embedding_profile,
    table_search_embedding_profile,
)
from app.tools.repository.statistics_search_repository import StatisticsSearchRepository
from utils.publication_kind import (
    DEFAULT_PUBLICATION_KIND,
    NO_PUBLICATION_PERIOD,
    normalize_publication_kind,
    normalize_publication_period_filter,
    publication_period_label,
)


SEARCH_TEXT_COLUMNS = (
    "ref_id",
    "chapter",
    "section",
    "level3_title",
    "level4_title",
    "title_ko",
    "title_en",
)
# RRF 논문의 관례값은 60이지만 그건 후보가 수천 건인 목록을 전제한다. 여기서 각 경로가 주는
# 후보는 max(20, limit*5)로 20~100건뿐이라 K=60이면 1위와 25위의 점수 차가 1.4배도 안 되어
# 순위 정보가 거의 지워지고, "몇 개 경로에 걸렸나"만 남아 제목이 정확히 맞는 표가 본문에 검색어가
# 흩어져 있는 표에 밀린다. K를 후보 수에 맞춰 낮추면 순위가 다시 의미를 갖는다.
# 질의 74개 평가에서 K=5~10이 같은 최고점이고 K>=12부터 떨어지므로 그 구간의 위쪽을 쓴다.
RRF_K = 10
TITLE_WEIGHT = 1.0
TABLE_VECTOR_WEIGHT = 1.8
TABLE_LEXICAL_WEIGHT = 3.0
# 주석은 표의 수치를 해석할 때 참고하는 보조 근거이므로 표 항목보다 낮게 잡는다.
# 대신 점수 칸을 따로 써서 항목과 주석이 함께 맞은 통계가 한쪽만 맞은 통계보다 높아지게 한다.
NOTE_VECTOR_WEIGHT = 1.0
NOTE_LEXICAL_WEIGHT = 1.2
EXACT_LABEL_BONUS = 0.05
LABEL_TOKEN_BONUS = 0.04
CHUNK_MATCH_SOURCES = {
    "headers": "column",
    "labels": "row_label",
    "notes": "footnote",
}
# 같은 통계는 정규화한 제목으로 판을 잇고, 통계마다 그 제목이 실린 가장 최근 발간판만
# 검색 대상으로 남긴다. 목차 번호(ref_id)는 발간판마다 다시 매겨지고 앞 판의 번호를 다른
# 통계가 물려받으므로 판을 잇는 키로 쓸 수 없다. 번호로 묶으면 번호를 뺏긴 구판 통계가
# 검색에서 통째로 빠진다.
# 최신 발간판에 같은 제목이 여러 건 실려 있으면(예: 이름은 같고 단위가 다른 별개 통계)
# 그 판의 해당 제목 통계를 모두 남긴다. 한 건만 남기면 나머지가 검색되지 않는다.
# 제목을 정규화해도 비어 있는 통계는 stat_id로 각자 묶어 서로를 가리지 않게 한다.
# 발간연도로 판을 고르므로 한 연도에 발간물이 하나라는 전제(publications.year UNIQUE)에
# 기댄다. 한 연도에 여러 발간물을 적재하려면 그룹 키에 발간물 구분을 함께 넣어야 한다.
SEARCH_REPOSITORY = StatisticsSearchRepository()
_QUERY_STOP_TOKENS = {
    "알려줘",
    "알려주세요",
    "보여줘",
    "보여주세요",
    "찾아줘",
    "찾아주세요",
    "검색해줘",
    "검색해주세요",
    "통계",
    "현황",
}


# 질의를 두 글자 이상의 검색 토큰으로 나눈다.
def _tokenize(query: str) -> list[str]:
    raw = re.split(r"[\s,()·/]+", query.strip())
    return [token.strip() for token in raw if len(token.strip()) >= 2]


# 검색 의도와 무관한 요청 표현과 연도 토큰을 제거한다.
def _lexical_query(query: str) -> str:
    tokens = [
        token
        for token in _tokenize(query)
        if token not in _QUERY_STOP_TOKENS
        and not re.fullmatch(r"\d{4}년?", token)
    ]
    return " ".join(tokens)


# 후보 행의 검색 대상 필드를 비교 가능한 단일 문자열로 합친다.
def _row_text(row: dict) -> str:
    values = [row.get(column) or "" for column in SEARCH_TEXT_COLUMNS]
    values.append(row.get("matched_text") or "")
    return " ".join(map(str, values)).lower()


# 후보 행에 실제로 포함된 원문 질의 토큰만 추린다.
def _matched_tokens(tokens: list[str], row: dict) -> list[str]:
    text = _row_text(row)
    return [token for token in tokens if token.lower() in text]


# DB의 JSON 또는 배열 라벨 값을 문자열 목록으로 정규화한다.
def _labels(row: dict) -> list[str]:
    labels = row.get("search_labels") or []
    if isinstance(labels, str):
        labels = json.loads(labels)
    return [str(label) for label in labels]


# 띄어쓰기와 구분자를 제거해 라벨 부분 일치를 비교하기 쉽게 만든다.
def _compact_match_text(value: str) -> str:
    return re.sub(r"[\s·･_/-]+", "", value.casefold())


# 질의 토큰과 가장 잘 맞는 표 라벨 및 일치 범위를 계산한다.
def _best_matched_text(
    query: str,
    row: dict,
) -> tuple[str | None, bool, float]:
    labels = _labels(row)
    if not labels:
        return None, False, 0.0
    lexical = _lexical_query(query).casefold()
    if lexical:
        for label in labels:
            if lexical in label.casefold():
                return label, True, 1.0
    search_tokens = _tokenize(_lexical_query(query))
    compact_tokens = [_compact_match_text(token) for token in search_tokens]

    # 정규화한 라벨에 포함된 질의 토큰 수를 센다.
    def matched_count(label: str) -> int:
        compact_label = _compact_match_text(label)
        return sum(token in compact_label for token in compact_tokens)

    ranked = sorted(
        labels,
        key=lambda label: (matched_count(label), len(label)),
        reverse=True,
    )
    matched = ranked[0]
    count = matched_count(matched)
    coverage = count / len(compact_tokens) if compact_tokens else 0.0
    exact = bool(compact_tokens) and count == len(compact_tokens)
    return matched, exact, coverage


# 통계 행을 여러 검색 경로가 공유할 랭킹 후보로 초기화한다.
def _base_candidate(row: dict) -> dict:
    return {
        "stat_id": row["stat_id"],
        "publication_kind": row.get("publication_kind", DEFAULT_PUBLICATION_KIND),
        "publication_period": row.get("publication_period", NO_PUBLICATION_PERIOD),
        "publication_year": row["publication_year"],
        "ref_id": row["ref_id"],
        "chapter_no": row["chapter_no"],
        "section_no": row["section_no"],
        "level3_no": row["level3_no"],
        "level4_no": row["level4_no"],
        "chapter": row["chapter"],
        "section": row["section"],
        "level3_title": row["level3_title"],
        "level4_title": row["level4_title"],
        "title_ko": row["title_ko"],
        "title_en": row["title_en"],
        "unit": row["unit"],
        "base_date": row["base_date"],
        "page_start": row["page_start"],
        # 조회 경로가 이 값을 주지 않으면 표가 있는 쪽으로 가정해 후보를 괜히 막지 않는다.
        "has_tables": bool(row.get("has_tables", True)),
        "table_seq": None,
        "matched_source": "title",
        "matched_text": row.get("title_ko"),
        "_priority": 1,
        "_score": 0.0,
        "_source_scores": {},
    }


# 검색 경로별 최고 기여도와 우선순위가 높은 일치 메타데이터를 반영한다.
def _add_candidate(
    candidates: dict[int, dict],
    row: dict,
    contribution: float,
    matched_source: str,
    matched_text: str | None,
    priority: int,
    score_source: str,
) -> None:
    stat_id = int(row["stat_id"])
    candidate = candidates.setdefault(stat_id, _base_candidate(row))
    previous = float(candidate["_source_scores"].get(score_source, 0.0))
    if contribution > previous:
        candidate["_score"] += contribution - previous
        candidate["_source_scores"][score_source] = contribution
    if priority > candidate["_priority"]:
        candidate["_priority"] = priority
        candidate["matched_source"] = matched_source
        candidate["matched_text"] = matched_text
        candidate["table_seq"] = row.get("table_seq")


# 세 후보군을 가중 RRF로 합치고 같은 통계표를 중복 제거한다.
def _merge_candidates(
    query: str,
    title_rows: list[dict],
    lexical_rows: list[dict],
    vector_rows: list[dict],
    limit: int,
) -> list[dict]:
    tokens = _tokenize(query)
    candidates: dict[int, dict] = {}

    for rank, row in enumerate(title_rows, start=1):
        _add_candidate(
            candidates,
            row,
            TITLE_WEIGHT / (RRF_K + rank),
            "title",
            row.get("title_ko"),
            1,
            "title",
        )

    for rank, row in enumerate(lexical_rows, start=1):
        matched_text, exact, coverage = _best_matched_text(query, row)
        source = CHUNK_MATCH_SOURCES.get(row["chunk_kind"], "row_label")
        is_note = source == "footnote"
        weight = NOTE_LEXICAL_WEIGHT if is_note else TABLE_LEXICAL_WEIGHT
        contribution = weight / (RRF_K + rank)
        contribution += LABEL_TOKEN_BONUS * coverage
        # 주석은 문장이라 질의가 통째로 들어가기 쉬우므로 완전 일치 가산은 주지 않는다.
        if exact and not is_note:
            contribution += EXACT_LABEL_BONUS
        _add_candidate(
            candidates,
            row,
            contribution,
            source,
            matched_text,
            2 if is_note else (5 if exact and source == "column" else 4),
            "note_lexical" if is_note else "lexical",
        )

    for rank, row in enumerate(vector_rows, start=1):
        matched_text, _exact, coverage = _best_matched_text(query, row)
        source = CHUNK_MATCH_SOURCES.get(row["chunk_kind"], "row_label")
        is_note = source == "footnote"
        weight = NOTE_VECTOR_WEIGHT if is_note else TABLE_VECTOR_WEIGHT
        _add_candidate(
            candidates,
            row,
            weight / (RRF_K + rank) + LABEL_TOKEN_BONUS * coverage,
            source,
            matched_text,
            2 if is_note else (3 if source == "column" else 2),
            "note_vector" if is_note else "table_vector",
        )

    ranked_results = sorted(
        candidates.values(),
        key=lambda item: (
            -item["_score"],
            -int(item["publication_year"]),
            int(item["stat_id"]),
        ),
    )
    results = []
    seen_tables: set[tuple[str, str]] = set()
    for candidate in ranked_results:
        semantic_key = (str(candidate.get("ref_id")), str(candidate.get("title_ko")))
        if semantic_key in seen_tables:
            continue
        seen_tables.add(semantic_key)
        results.append(candidate)
        if len(results) == limit:
            break
    for result in results:
        result["score"] = round(result.pop("_score"), 6)
        result.pop("_priority", None)
        result.pop("_source_scores", None)
        result["matched_tokens"] = _matched_tokens(tokens, result)
    return results


# 검색할 수 없는 질의에 대해 일관된 빈 응답을 만든다.
def _empty_response(
    query: str,
    publication_year: int | None = None,
    publication_kind: str = DEFAULT_PUBLICATION_KIND,
    publication_period: str | None = None,
) -> dict:
    return {
        "query": query,
        "tokens": [],
        "requested_publication_kind": publication_kind,
        "applied_publication_kind": publication_kind,
        "requested_publication_period": publication_period,
        "applied_publication_period": publication_period,
        "requested_publication_year": publication_year,
        "applied_publication_year": publication_year,
        "latest_edition_per_statistic": False,
        "publication_year_filter_relaxed": False,
        "message": None,
        "count": 0,
        "results": [],
    }


# 적용한 발간판 범위를 모델이 그대로 인용할 수 있는 안내 문구로 만든다.
def _publication_scope_message(
    latest_editions: bool,
    filter_relaxed: bool,
    publication_period: str | None = None,
    empty: bool = False,
) -> str | None:
    if empty and publication_period is not None:
        label = publication_period_label(publication_period)
        return (
            f"{label} 발간판에는 후보가 없습니다. 반기를 지정하지 않고 다시 검색하면 "
            "같은 해의 다른 반기까지 함께 찾습니다."
        )
    if filter_relaxed:
        return (
            "요청한 발간연도에는 후보가 없어 통계별 최신 발간판으로 재검색했습니다. "
            "각 결과의 publication_year가 실제 발간판입니다."
        )
    if latest_editions:
        return (
            "발간연도를 지정하지 않아 통계마다 가장 최근 발간판을 적용했습니다. "
            "통계별로 최신 발간판이 다를 수 있으므로 각 결과의 publication_year를 사용하세요."
        )
    return None


# 자연어 질의를 임베딩하고 후보군을 결합해 최종 통계 검색 결과를 만든다.
# 발간연도를 지정하지 않으면 통계마다 가장 최근 발간판만 검색해 구판에만 있는 통계도 찾는다.
# 지정 연도에 결과가 없을 때만 같은 최신판 범위로 한 번 더 검색한다.
def search_statistics_data(
    query: str,
    publication_year: int | None = None,
    limit: int = 5,
    publication_kind: str = DEFAULT_PUBLICATION_KIND,
    publication_period: str | None = None,
) -> dict:
    publication_kind = normalize_publication_kind(publication_kind)
    publication_period = normalize_publication_period_filter(publication_period)
    if not query or not query.strip():
        return _empty_response(query, publication_year, publication_kind, publication_period)

    requested_publication_year = publication_year
    latest_editions = publication_year is None

    tokens = _tokenize(query)
    semantic_query = _lexical_query(query) or query.strip()
    query_vec = embed_query(semantic_query)
    title_profile_key = embedding_profile().profile_key
    table_profile_key = table_search_embedding_profile().profile_key
    rows = SEARCH_REPOSITORY.fetch_rows(
        semantic_query,
        query_vec,
        title_profile_key,
        table_profile_key,
        publication_year,
        latest_editions,
        limit,
        publication_kind=publication_kind,
        publication_period=publication_period,
    )
    results = _merge_candidates(query, *rows, limit)
    filter_relaxed = False

    if not results and requested_publication_year is not None:
        latest_editions = True
        rows = SEARCH_REPOSITORY.fetch_rows(
            semantic_query,
            query_vec,
            title_profile_key,
            table_profile_key,
            None,
            latest_editions,
            limit,
            publication_kind=publication_kind,
            publication_period=publication_period,
        )
        results = _merge_candidates(query, *rows, limit)
        filter_relaxed = True

    return {
        "query": query,
        "tokens": tokens,
        "requested_publication_kind": publication_kind,
        "applied_publication_kind": publication_kind,
        "requested_publication_period": publication_period,
        "applied_publication_period": publication_period,
        "requested_publication_year": requested_publication_year,
        "applied_publication_year": None if latest_editions else publication_year,
        "latest_edition_per_statistic": latest_editions,
        "publication_year_filter_relaxed": filter_relaxed,
        "message": _publication_scope_message(
            latest_editions,
            filter_relaxed,
            publication_period,
            not results,
        ),
        "count": len(results),
        "results": results,
    }
