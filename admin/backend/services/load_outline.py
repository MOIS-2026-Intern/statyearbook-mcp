# 이 파일은 통계연보의 목차 계층(장/절/3계층/4계층)을 복원한다.
# 본문 표제 표를 계층의 정본으로 삼고, 앞머리 목차 표는 장·절 이름과 교차검증에만 쓴다.
#
# 본문과 목차가 어긋나는 실제 사례가 있어 이런 역할 분담이 필요하다.
# 2026년 연보 목차에는 본문에서 빠진 항목(예: "4-2-1 지역주도형 청년일자리 사업 실적",
# 페이지 번호가 "?")이 남아 있어 그 뒤의 모든 leaf 번호가 본문보다 하나씩 밀린다.
# 반대로 본문 표제 번호는 두 해 모두 빠짐·중복·역순이 없어 정본으로 쓸 수 있다.
from __future__ import annotations

import re
from dataclasses import dataclass, field

APPENDIX_CHAPTER_NO = 9
APPENDIX_CHAPTER_TITLE = "부록"

# 본문 표제 표의 첫 토큰에서 계층 번호를 읽는 패턴이다.
RE_HEAD_L4 = re.compile(r"^(\d+)-(\d+)-(\d+)-(\d+)(?![\d-])")
RE_HEAD_L3 = re.compile(r"^(\d+)-(\d+)-(\d+)(?![\d-])")
RE_HEAD_APPENDIX_L4 = re.compile(r"^부록\s*(\d+)\s*-\s*(\d+)(?![\d-])")
RE_HEAD_APPENDIX_L3 = re.compile(r"^부록\s*(\d+)(?![\d-])")

# 절 표지 표는 "제N절" 한 셀과 국·영문 제목 셀로 이루어진다.
RE_SECTION_COVER = re.compile(r"^제\s*(\d+)\s*절$")

# 목차 셀 안에서 절·3계층·4계층 줄을 구분하는 패턴이다.
RE_TOC_SECTION = re.compile(r"^제\s*(\d+)\s*절\s+(.+)$")
RE_TOC_L3 = re.compile(r"^(\d+)-(\d+)-(\d+)\s+(.+)$")
RE_TOC_L4 = re.compile(r"^(\d+)\.\s+(.+)$")
RE_TOC_APPENDIX = re.compile(r"^부록\s*(\d+)\s+(.+)$")

# 목차 줄 끝의 인쇄 페이지 번호. 본문에서 빠진 항목은 페이지가 "?"로 남아 있다.
RE_TOC_PAGE = re.compile(r"\s+(\d{1,4}|\?)$")

RE_HANGUL = re.compile(r"[가-힣]")
RE_LATIN = re.compile(r"[A-Za-z]")
RE_LOWER = re.compile(r"[a-z]")

# 판권지(인쇄·발행 정보) 표는 통계가 아니므로 본문 순회를 여기서 끝낸다.
COLOPHON_HINTS = ("인 쇄", "발행처", "발 행")


# 문서에서 복원한 하나의 통계 leaf. ref_id는 본문 표제 번호를 그대로 쓴다.
@dataclass
class OutlineNode:
    ref_id: str
    ordinal: int
    chapter_no: int | None
    section_no: int | None
    level3_no: int | None
    level4_no: int | None
    chapter: str | None
    section: str | None
    level3_title: str | None
    level3_title_en: str | None
    level4_title: str | None
    level4_title_en: str | None
    page_start: int | None


# 본문 표제 표 한 셀을 해석한 결과다. level 3은 묶음 제목, level 4는 하위 제목이다.
@dataclass
class Heading:
    level: int
    ref_id: str
    chapter_no: int | None
    section_no: int | None
    level3_no: int | None
    level4_no: int | None
    title_ko: str | None
    title_en: str | None


# 목차에서 읽은 장·절 이름과 leaf 목록. leaf는 교차검증 리포트에만 쓴다.
@dataclass
class TocCatalog:
    chapters: dict[int, tuple[str, str | None]] = field(default_factory=dict)
    sections: dict[tuple[int, int], tuple[str, str | None]] = field(default_factory=dict)
    leaves: list[dict] = field(default_factory=list)


# 줄바꿈과 반복 공백만 정리해 제목 비교에 쓸 한 줄 문자열을 만든다.
def _flatten(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


# 목차 줄 끝의 인쇄 페이지 번호를 떼어내고 값이 "?"면 페이지 없음으로 본다.
def _split_toc_page(line: str) -> tuple[str, int | None]:
    match = RE_TOC_PAGE.search(line)
    if not match:
        return line.strip(), None
    page = match.group(1)
    return line[: match.start()].strip(), (int(page) if page.isdigit() else None)


# 꼬리 토큰들이 영문 제목으로 볼 만한지 판정한다.
# 통계 제목에서는 "1인당 GRDP"처럼 국문 제목 끝의 약어 하나를 영문 제목으로 잘라내면 안 되므로
# 두 토큰 이상이거나 소문자가 섞인 경우만 영문 제목으로 본다.
# 장·절 제목은 언제나 "국문 대문자영문" 꼴이라 "기타 OTHERS"처럼 한 토큰짜리도 허용한다.
def _looks_like_english_title(tokens: list[str], allow_single_token: bool) -> bool:
    if not tokens or not any(RE_LATIN.search(token) for token in tokens):
        return False
    if allow_single_token or len(tokens) >= 2:
        return True
    return any(RE_LOWER.search(token) for token in tokens)


# 한 줄 또는 여러 줄 제목을 국문과 영문으로 나눈다.
# 줄바꿈이 국·영문 경계면 그것을 쓰고, 아니면 한글이 없는 가장 긴 꼬리를 영문 제목으로 본다.
# "지역별 지자체 CCTV 통합관제센터 운영 현황 CCTV Control Center Operations by Local Government"처럼
# 국문 안에 약어가 섞여도 마지막 한글 토큰 뒤에서 잘리므로 안전하다.
def split_title(raw: str, allow_single_token_en: bool = False) -> tuple[str | None, str | None]:
    text = (raw or "").strip()
    if not text:
        return None, None

    if "\n" in text:
        head, tail = text.split("\n", 1)
        ko, en = _flatten(head), _flatten(tail)
        if ko and en and not RE_HANGUL.search(en):
            return ko, en

    flat = _flatten(text)
    if not flat:
        return None, None
    if not RE_HANGUL.search(flat):
        # 쪽이 넘어가며 영문 제목만 다시 실린 표제다.
        return None, flat

    tokens = flat.split(" ")
    cut = len(tokens)
    while cut > 0 and not RE_HANGUL.search(tokens[cut - 1]):
        cut -= 1
    tail_tokens = tokens[cut:]
    if _looks_like_english_title(tail_tokens, allow_single_token_en):
        return " ".join(tokens[:cut]) or None, " ".join(tail_tokens)
    return flat, None


# 한글이 전혀 없고 영문자가 있으면 국문 없이 영문 제목만 실린 표제로 본다.
def is_english_only(text: str) -> bool:
    return not re.search(r"[가-힣]", text or "") and bool(re.search(r"[A-Za-z]", text or ""))


# 본문 1열 표의 셀 하나를 표제(3계층/4계층)로 해석한다. 표제가 아니면 None을 준다.
def parse_heading_cell(text: str) -> Heading | None:
    text = (text or "").strip()
    if not text:
        return None

    match = RE_HEAD_L4.match(text)
    if match:
        chapter, section, level3, level4 = (int(g) for g in match.groups())
        ko, en = split_title(text[match.end():])
        return Heading(4, match.group(0), chapter, section, level3, level4, ko, en)

    match = RE_HEAD_L3.match(text)
    if match:
        chapter, section, level3 = (int(g) for g in match.groups())
        ko, en = split_title(text[match.end():])
        return Heading(3, match.group(0), chapter, section, level3, None, ko, en)

    match = RE_HEAD_APPENDIX_L4.match(text)
    if match:
        level3, level4 = int(match.group(1)), int(match.group(2))
        ko, en = split_title(text[match.end():])
        ref_id = f"부록{level3}-{level4}"
        return Heading(4, ref_id, APPENDIX_CHAPTER_NO, None, level3, level4, ko, en)

    match = RE_HEAD_APPENDIX_L3.match(text)
    if match:
        level3 = int(match.group(1))
        ko, en = split_title(text[match.end():])
        return Heading(3, f"부록{level3}", APPENDIX_CHAPTER_NO, None, level3, None, ko, en)

    return None


# 판권지처럼 통계가 아닌 마감 표인지 판별해 본문 순회를 끝낼 지점을 찾는다.
def is_colophon(table_text: str) -> bool:
    return sum(1 for hint in COLOPHON_HINTS if hint in table_text) >= 2


# 1열 표의 셀 목록이 절 표지("제N절" + 국·영문 제목)인지 확인한다.
def parse_section_cover(cells: list[str]) -> tuple[int, str, str | None] | None:
    values = [_flatten(cell) for cell in cells if _flatten(cell)]
    if len(values) < 2:
        return None
    match = RE_SECTION_COVER.match(values[0])
    if not match:
        return None
    title_en = values[2] if len(values) > 2 else None
    return int(match.group(1)), values[1], title_en


# 목차 표의 한 행이 "장 번호 + 장 제목"인지 확인한다.
def parse_toc_chapter_row(cells: list[str]) -> tuple[int, str, str | None] | None:
    values = [cell.strip() for cell in cells]
    if not values or not values[0].strip().isdigit():
        return None
    raw = next((value for value in values[1:] if value.strip()), "")
    if not raw:
        return None
    ko, en = split_title(raw, allow_single_token_en=True)
    return int(values[0].strip()), ko or raw, en


# 목차 셀 본문을 줄 단위로 읽어 절·3계층·4계층 항목을 순서대로 복원한다.
def _consume_toc_lines(catalog: TocCatalog, chapter_no: int, cell_text: str) -> None:
    lines = [line.strip() for line in cell_text.splitlines()]
    lines = [line for line in lines if line]
    section_no: int | None = None
    level3: dict | None = None
    index = 0

    # 제목 줄 다음이 영문 전용 줄이면 그 줄을 영문 제목으로 흡수한다.
    def take_english(position: int) -> tuple[str | None, int]:
        if position < len(lines) and is_english_only(lines[position]):
            return _split_toc_page(lines[position])[0], position + 1
        return None, position

    while index < len(lines):
        line = lines[index]
        index += 1

        match = RE_TOC_SECTION.match(line)
        if match:
            section_no = int(match.group(1))
            ko, en = split_title(
                _split_toc_page(match.group(2))[0], allow_single_token_en=True
            )
            catalog.sections.setdefault((chapter_no, section_no), (ko or "", en))
            level3 = None
            continue

        match = RE_TOC_L3.match(line)
        if match:
            body, page = _split_toc_page(match.group(4))
            ko, en = split_title(body)
            if en is None:
                en, index = take_english(index)
            level3 = {
                "ref_id": f"{match.group(1)}-{match.group(2)}-{match.group(3)}",
                "chapter_no": int(match.group(1)),
                "section_no": int(match.group(2)),
                "level3_no": int(match.group(3)),
                "title_ko": ko,
                "title_en": en,
                "page": page,
                "children": 0,
            }
            catalog.leaves.append(level3)
            continue

        match = RE_TOC_APPENDIX.match(line)
        if match and chapter_no == APPENDIX_CHAPTER_NO:
            body, page = _split_toc_page(match.group(2))
            ko, en = split_title(body)
            if en is None:
                en, index = take_english(index)
            level3 = {
                "ref_id": f"부록{match.group(1)}",
                "chapter_no": APPENDIX_CHAPTER_NO,
                "section_no": None,
                "level3_no": int(match.group(1)),
                "title_ko": ko,
                "title_en": en,
                "page": page,
                "children": 0,
            }
            catalog.leaves.append(level3)
            continue

        match = RE_TOC_L4.match(line)
        if match and level3 is not None:
            body, page = _split_toc_page(match.group(2))
            ko, en = split_title(body)
            if en is None:
                en, index = take_english(index)
            level3["children"] += 1
            catalog.leaves.append({
                "ref_id": f'{level3["ref_id"]}-{match.group(1)}',
                "chapter_no": level3["chapter_no"],
                "section_no": level3["section_no"],
                "level3_no": level3["level3_no"],
                "level4_no": int(match.group(1)),
                "title_ko": ko,
                "title_en": en,
                "page": page,
                "parent": level3["ref_id"],
            })
            continue


# 앞머리 목차 표들에서 장 이름, 절 이름과 leaf 목록을 읽어 catalog를 만든다.
def build_toc_catalog(toc_tables: list[dict]) -> TocCatalog:
    catalog = TocCatalog()
    for table in toc_tables:
        chapter_no: int | None = None
        for row in table.get("cells", []):
            texts = [cell.get("text") or "" for cell in row]
            chapter_row = parse_toc_chapter_row(texts)
            if chapter_row:
                chapter_no, title_ko, title_en = chapter_row
                catalog.chapters.setdefault(chapter_no, (title_ko, title_en))
                continue
            if chapter_no is None:
                continue
            for text in texts:
                if text.strip():
                    _consume_toc_lines(catalog, chapter_no, text)
    catalog.chapters.setdefault(APPENDIX_CHAPTER_NO, (APPENDIX_CHAPTER_TITLE, None))
    return catalog


# 본문 표제 순서대로 leaf를 확정한다. 하위 제목이 있으면 4계층이, 없으면 3계층이 leaf다.
def build_outline(
    headings: list[tuple[Heading, int | None]],
    catalog: TocCatalog,
    section_covers: dict[tuple[int, int], tuple[str, str | None]],
) -> tuple[list[OutlineNode], dict[str, OutlineNode]]:
    groups: dict[str, Heading] = {}
    children: dict[str, int] = {}
    for heading, _ in headings:
        if heading.level == 3:
            groups[heading.ref_id] = heading
            children.setdefault(heading.ref_id, 0)
        else:
            parent = heading.ref_id.rsplit("-", 1)[0]
            children[parent] = children.get(parent, 0) + 1

    # 장 이름은 ref_id의 장 번호로만 정한다. 본문 표지 순서에 기대면 장이 뒤섞인다.
    def chapter_title(chapter_no: int | None) -> str | None:
        if chapter_no is None:
            return None
        return (catalog.chapters.get(chapter_no) or (None, None))[0]

    # 절 이름은 본문 절 표지를 우선하고 없으면 목차의 "제N절" 줄을 쓴다.
    def section_title(chapter_no: int | None, section_no: int | None) -> str | None:
        if chapter_no is None or section_no is None:
            return None
        key = (chapter_no, section_no)
        found = section_covers.get(key) or catalog.sections.get(key)
        return found[0] if found else None

    nodes: list[OutlineNode] = []
    by_ref: dict[str, OutlineNode] = {}
    for heading, page in headings:
        if heading.level == 3 and children.get(heading.ref_id, 0) > 0:
            continue
        if heading.ref_id in by_ref:
            continue

        if heading.level == 4:
            parent_ref = heading.ref_id.rsplit("-", 1)[0]
            parent = groups.get(parent_ref)
            level3_ko = parent.title_ko if parent else None
            level3_en = parent.title_en if parent else None
            level4_ko, level4_en = heading.title_ko, heading.title_en
        else:
            level3_ko, level3_en = heading.title_ko, heading.title_en
            level4_ko, level4_en = None, None

        node = OutlineNode(
            ref_id=heading.ref_id,
            ordinal=len(nodes) + 1,
            chapter_no=heading.chapter_no,
            section_no=heading.section_no,
            level3_no=heading.level3_no,
            level4_no=heading.level4_no,
            chapter=chapter_title(heading.chapter_no),
            section=section_title(heading.chapter_no, heading.section_no),
            level3_title=level3_ko,
            level3_title_en=level3_en,
            level4_title=level4_ko,
            level4_title_en=level4_en,
            page_start=page,
        )
        nodes.append(node)
        by_ref[node.ref_id] = node
    return nodes, by_ref
