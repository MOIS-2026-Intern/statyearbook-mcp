# 이 파일은 주요통계집 HWPX를 통계연보와 같은 적재 포맷으로 파싱한다.
#
# 주요통계집은 통계연보와 계층 표기가 다르다. 통계연보는 "1-2-3-4"처럼 본문 표제 표에
# 번호가 찍혀 있지만, 주요통계집은 장 표지에 장 번호만 있고 본문 항목은 "4-38 서해 5도"
# 처럼 장-항목 두 단계뿐이다. 그 아래 실제 통계는 번호 없이 두 가지 방식으로 적힌다.
#
#   ❍ 서해 5도 인구 : 8,151명(남 4,860 / 여 3,291)   <- 3계층. 제목 자체가 값을 담는다.
#     - 연평면 1,993 / 백령면 4,722 / 대청면 1,436    <- 그 3계층의 내용
#     ※ 옹진군 전체 인구(19,996명)의 40.8%            <- 그 3계층의 주석
#   < 지구촌 새마을운동 현황 >                        <- 4계층. 바로 아래 표의 실제 제목
#
# 그래서 한 항목(4-38)은 통계 하나가 아니라 ❍/<> 묶음마다 하나씩 통계 행이 된다.
# chapter_no=4, section_no=38, section="서해 5도"가 항목을 가리키고 level3_title에 ❍
# 제목이, level4_title에 <> 제목이 들어간다. 문서에 번호가 없으므로 level3_no와
# level4_no는 비운다.
#
# 표가 없는 ❍ 묶음도 본문에 수치가 그대로 적혀 있으므로 내용 줄을 한 컬럼짜리 표로 만들어
# stat_tables.table_md와 body에 넣는다. 그래야 표 검색·임베딩이 같은 경로로 동작한다.
from __future__ import annotations

import os
import re
import zipfile

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from admin.backend.services.load_parser import (
    HP,
    RE_SECTION_XML,
    check_units,
    clean_text,
    parse_table,
    records_to_markdown,
    section_names,
    table_record,
    visible_text,
)
from utils.publication_kind import (
    MAJOR_STATISTICS_KIND,
    NO_PUBLICATION_PERIOD,
    normalize_publication_kind,
    normalize_publication_period,
    publication_period_label,
)


# 항목 번호는 "4-38"처럼 장-항목 두 단계이며 참고자료 장만 "참고-1" 꼴을 쓴다.
RE_ITEM_ID = re.compile(r"^(?P<chapter>\d{1,2})\s*-\s*(?P<item>\d{1,3})$")
RE_REFERENCE_ID = re.compile(r"^참고\s*-\s*(?P<item>\d{1,3})$")
RE_CHAPTER_NO = re.compile(r"^(\d{1,2})$")
# 앞머리 목차 줄. "4-38. 서해 5도 217"처럼 번호, 제목, 인쇄 쪽 번호가 한 줄에 있다.
RE_TOC_ENTRY = re.compile(
    r"^(?P<ref>\d{1,2}\s*-\s*\d{1,3}|참고\s*-\s*\d{1,3})\s*\.\s*(?P<title>.+?)\s+(?P<page>\d{1,4})$"
)
# 항목 제목 아래에 붙는 기준일. "('25.9.16.)"처럼 두 자리 연도로만 적힌다.
RE_ITEM_DATE = re.compile(
    r"^\(?\s*['’‘]?(?P<year>\d{2})\s*\.\s*(?P<month>\d{1,2})\s*\.\s*(?P<day>\d{1,2})\s*\.?\s*\)?$"
)
RE_UNIT_LINE = re.compile(r"^\(?\s*단위\s*[:：]\s*(?P<unit>[^)]+?)\s*\)?$")
# 3계층 표제. 문서에 실제로 쓰인 글머리표만 받는다.
RE_LEVEL3 = re.compile(r"^[❍○◯◦●]\s*(?P<title>.+)$")
# 4계층 표제. 표 바로 위에 "< 기부 추이 >" 꼴로 적힌 표의 실제 제목이다.
RE_LEVEL4 = re.compile(r"^[<〈＜]\s*(?P<title>[^<>〈〉＜＞]+?)\s*[>〉＞]$")
RE_NOTE = re.compile(r"^(?:주\s*\d*\s*\)|※|＊|\*|출처\s*[:：])")
RE_PHONE = re.compile(r"0\d{1,2}[-)]\s?\d{3,4}[-]\d{4}")

# 그림·묶음 개체 자리에 한글이 남기는 대체 문구다. 본문 내용이 아니므로 버린다.
OBJECT_PLACEHOLDERS = (
    "묶음 개체입니다.",
    "그림입니다.",
    "표입니다.",
    "사각형입니다.",
    "글상자입니다.",
)
# 판권지는 통계가 아니라 인쇄·발행 정보다. 두 낱말 이상 걸리면 본문에서 뺀다.
COLOPHON_HINTS = ("발행일", "발행처", "제작사", "문의처", "인 쇄")
CONTACT_BULLETS = ("•", "●", "∙", "・")
CONTACT_ROLE_WORDS = (
    "과장",
    "팀장",
    "사무관",
    "서기관",
    "주무관",
    "전문관",
    "연구관",
    "연구사",
)
# 한 컬럼짜리 본문 표의 머리글. 표 검색 청크가 컬럼명을 요구하므로 고정 이름을 쓴다.
TEXT_TABLE_COLUMN = "내용"
# 1행 1열 표는 표가 아니라 본문을 감싼 글상자다. 줄로 풀어 내용에 합친다.
TEXT_BOX_ROWS = 1
TEXT_BOX_COLS = 1


# 한 항목 안에서 통계 행 하나가 될 ❍ 또는 <> 묶음이다.
@dataclass
class ContentBlock:
    level3_title: str | None = None
    level4_title: str | None = None
    lines: list[str] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unit: str | None = None

    # 표, 본문 줄, 주석 중 하나라도 있으면 그 자체로 통계 행이 될 내용이 있다고 본다.
    def has_content(self) -> bool:
        return bool(self.lines or self.tables or self.notes)


# 본문의 한 항목("4-38 서해 5도")이다. 아래의 묶음들이 각각 통계 행이 된다.
@dataclass
class BodyItem:
    item_id: str
    chapter_no: int | None
    section_no: int | None
    title: str
    page: int | None = None
    base_date: str | None = None
    blocks: list[ContentBlock] = field(default_factory=list)
    contacts: list[dict] = field(default_factory=list)


# 한글이 개체 자리에 넣는 대체 문구인지 판정한다.
def is_placeholder(text: str) -> bool:
    return text.strip() in OBJECT_PLACEHOLDERS


# 문단이 담당 부서·담당자 줄인지 판정한다. 글머리표와 전화번호가 함께 있어야 한다.
def is_contact_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(CONTACT_BULLETS) and bool(RE_PHONE.search(stripped))


# 전화번호 표기를 하이픈 하나로 정규화한다.
def normalize_phone(value: str) -> str:
    return re.sub(r"-+", "-", value.replace(")", "-").replace(" ", "")).strip("-")


# 전화번호 앞 문구에서 부서명을 고른다. 직급 단어 앞까지가 부서명이다.
def department_from_prefix(prefix: str) -> str | None:
    tokens = prefix.split()
    if not tokens:
        return None
    for index, token in enumerate(tokens):
        if any(role in token for role in CONTACT_ROLE_WORDS):
            return " ".join(tokens[:index]) if index else tokens[0]
    return tokens[0]


# 한 줄에 여러 담당자가 적힌 출처 문단을 전화번호마다 하나씩의 연락처로 나눈다.
def parse_contact_line(text: str) -> list[dict]:
    body = text.lstrip("".join(CONTACT_BULLETS)).strip()
    phones = list(RE_PHONE.finditer(body))
    if not phones:
        return []
    dept = department_from_prefix(body[: phones[0].start()].strip())
    contacts: list[dict] = []
    previous_end = 0
    for phone_match in phones:
        officer = body[previous_end: phone_match.start()].strip(" (),;·")
        if dept and officer.startswith(dept):
            officer = officer[len(dept):].strip(" (),;·")
        contacts.append({
            "dept": dept,
            "officer": officer or None,
            "phone": normalize_phone(phone_match.group(0)),
            "source_system": None,
            "source_url": None,
        })
        previous_end = phone_match.end()
    return contacts


# 두 자리 연도로 적힌 기준일을 발간연도의 세기를 붙여 네 자리로 만든다.
def normalize_base_date(text: str, publication_year: int) -> str | None:
    match = RE_ITEM_DATE.match(text)
    if not match:
        return None
    century = publication_year // 100 * 100
    year = century + int(match.group("year"))
    return f"{year}.{int(match.group('month'))}.{int(match.group('day'))}."


# 항목 번호 문단을 장 번호와 항목 번호로 나눈다. 참고자료는 장 번호가 없다.
def parse_item_id(text: str) -> tuple[str, int | None, int] | None:
    match = RE_ITEM_ID.match(text)
    if match:
        chapter = int(match.group("chapter"))
        item = int(match.group("item"))
        return f"{chapter}-{item}", chapter, item
    match = RE_REFERENCE_ID.match(text)
    if match:
        item = int(match.group("item"))
        return f"참고-{item}", None, item
    return None


# 한 칸짜리 표는 수치 표가 아니라 본문을 감싼 글상자다. 줄로 풀어 본문처럼 다룬다.
def is_text_box(table: dict) -> bool:
    return (table.get("cols") or 0) <= TEXT_BOX_COLS


# 글상자 표의 셀 안에 줄바꿈으로 이어 붙은 본문을 줄 목록으로 되돌린다.
def text_box_lines(table: dict) -> list[str]:
    lines: list[str] = []
    for row in table.get("cells", []):
        for cell in row:
            for line in (cell.get("text") or "").splitlines():
                cleaned = clean_text(line)
                if cleaned and not is_placeholder(cleaned):
                    lines.append(cleaned)
    return lines


# 인쇄·발행 정보만 담긴 판권지인지 판정한다.
def is_colophon(lines: list[str]) -> bool:
    blob = " ".join(lines)
    return sum(1 for hint in COLOPHON_HINTS if hint in blob) >= 2


# 제목 자체가 수치를 담고 있는지 본다. 숫자나 콜론이 있으면 본문 표에도 남긴다.
def title_carries_data(title: str | None) -> bool:
    if not title:
        return False
    return bool(re.search(r"\d", title)) or ":" in title or "：" in title


# 본문 줄들을 한 컬럼짜리 표 레코드로 만든다. 표가 없는 ❍ 묶음의 내용을 담는 그릇이다.
def text_table_record(seq: int, caption: str | None, lines: list[str]) -> dict:
    columns = [TEXT_TABLE_COLUMN]
    records = [{TEXT_TABLE_COLUMN: line} for line in lines]
    grid = [columns] + [[line] for line in lines]
    body = {
        "kind": "text",
        "rows": len(grid),
        "cols": 1,
        "columns": columns,
        "records": records,
        "grid": grid,
    }
    return {
        "seq": seq,
        "caption": caption,
        "n_rows": len(grid),
        "n_cols": 1,
        "body": body,
        "table_md": records_to_markdown(columns, records),
    }


# 본문에 글자를 남기지 않는 개체다. 안쪽까지 건너뛴다.
SKIPPED_OBJECT_TAGS = {HP + "pic", HP + "ctrl"}


# HWPX 본문을 원래 읽는 순서대로 문단·표 block으로 흘려보낸다.
#
# 통계연보 파서의 iter_blocks는 최상위 hp:p만 훑고 hp:rect 안쪽을 건너뛴다. 주요통계집은
# 항목 제목과 번호가 묶음 개체 안의 글상자에 들어 있어 그대로 쓰면 항목 경계를 못 찾는다.
# 그래서 여기서는 글상자 안쪽 문단까지 내려가되 표 안의 문단만 제외한다. 표는 표 파서가
# 셀 단위로 따로 읽는다.
def iter_body_blocks(hwpx_path: str):
    with zipfile.ZipFile(hwpx_path) as zip_file:
        for section_name in section_names(zip_file):
            section_index = int(RE_SECTION_XML.match(section_name).group(1))
            root = ET.fromstring(zip_file.read(section_name))
            context = {
                "page": 1,
                "buffer": [],
                "section_name": section_name,
                "section_index": section_index,
            }
            yield from _walk_blocks(root, context)
            yield from _flush_text(context)


# 모아 둔 글자를 문단 block 하나로 비운다. 개체를 만나기 직전마다 호출한다.
def _flush_text(context: dict):
    text = clean_text("".join(context["buffer"]), keep_newlines=True)
    context["buffer"].clear()
    if text and not is_placeholder(text):
        yield {
            "type": "paragraph",
            "section_index": context["section_index"],
            "page": context["page"],
            "text": text,
        }


# 한 XML 노드 아래를 문서 순서대로 훑어 문단 텍스트와 표를 차례로 낸다.
# hp:p는 문단 경계이므로 들어가고 나올 때 모아 둔 글자를 비운다.
def _walk_blocks(node: ET.Element, context: dict):
    for child in node:
        tag = child.tag
        if tag in SKIPPED_OBJECT_TAGS:
            continue
        if tag == HP + "tbl":
            yield from _flush_text(context)
            yield {
                "type": "table",
                "section_index": context["section_index"],
                "page": context["page"],
                "table": parse_table(child, context["section_name"], context["page"]),
            }
            continue
        if tag == HP + "p":
            yield from _flush_text(context)
            if child.get("pageBreak") == "1":
                context["page"] += 1
            yield from _walk_blocks(child, context)
            yield from _flush_text(context)
            continue
        if tag == HP + "tab":
            context["buffer"].append(" ")
        elif tag == HP + "lineBreak":
            context["buffer"].append("\n")
        elif child.text:
            context["buffer"].append(child.text)
        yield from _walk_blocks(child, context)
        if child.tail:
            context["buffer"].append(child.tail)


# 앞머리 목차에서 장 이름과 항목별 제목·인쇄 쪽 번호를 읽는다.
def parse_table_of_contents(blocks: list[dict]) -> tuple[dict[int, str], dict[str, dict]]:
    chapters: dict[int, str] = {}
    entries: dict[str, dict] = {}
    pending_chapter_no: int | None = None
    for block in blocks:
        if block["type"] != "paragraph":
            continue
        text = clean_text(block["text"])
        match = RE_TOC_ENTRY.match(text)
        if match:
            parsed = parse_item_id(re.sub(r"\s+", "", match.group("ref")))
            if parsed:
                entries.setdefault(parsed[0], {
                    "title": clean_text(match.group("title")),
                    "page": int(match.group("page")),
                })
            pending_chapter_no = None
            continue
        number = RE_CHAPTER_NO.match(text)
        if number:
            pending_chapter_no = int(number.group(1))
            continue
        if pending_chapter_no is not None:
            chapters.setdefault(pending_chapter_no, text)
            pending_chapter_no = None
    return chapters, entries


# 본문 블록을 항목 단위로 자른다. 항목 번호 문단 바로 앞 문단이 항목 제목이다.
#
# 제목이 번호보다 먼저 나오므로 문단 하나를 붙들어 두고 다음 문단을 본 뒤에 처리한다.
# 곧바로 앞 항목의 내용으로 넣으면 다음 항목의 제목이 앞 항목 표에 섞여 들어간다.
def split_body_items(
    blocks: list[dict],
    publication_year: int,
    toc_chapters: dict[int, str] | None = None,
) -> tuple[list[BodyItem], dict[int, str], list[str]]:
    known_chapters = toc_chapters or {}
    items: list[BodyItem] = []
    chapters: dict[int, str] = {}
    warnings: list[str] = []
    pending_text: str | None = None
    pending_chapter_no: int | None = None
    current: BodyItem | None = None
    block_state: dict = {}

    # 장 표지는 장 번호 한 줄과 장 이름 한 줄로만 되어 있다. 본문에 우연히 섞인 숫자를
    # 표지로 오인하지 않도록 목차에서 읽은 장 번호일 때만 표지로 본다.
    def is_chapter_cover(text: str) -> bool:
        number = RE_CHAPTER_NO.match(text)
        if not number:
            return False
        return int(number.group(1)) in known_chapters if known_chapters else current is None

    # 붙들어 둔 문단이 다음 항목의 제목이 아니었으므로 지금 항목의 내용으로 넘긴다.
    def release_pending() -> None:
        nonlocal pending_text, pending_chapter_no, current
        text, pending_text = pending_text, None
        if text is None:
            return
        if pending_chapter_no is not None:
            chapters.setdefault(pending_chapter_no, text)
            pending_chapter_no = None
            return
        if is_chapter_cover(text):
            # 장이 바뀌면 앞 장의 마지막 항목은 여기서 끝난다.
            pending_chapter_no = int(text)
            current = None
            return
        if current is not None:
            _absorb_paragraph(current, text, block_state, publication_year)

    for block in blocks:
        if block["type"] == "table":
            release_pending()
            if current is not None:
                _absorb_table(current, block["table"], block_state, publication_year)
            continue

        text = clean_text(block["text"])
        if not text:
            continue

        parsed = parse_item_id(text)
        if parsed is not None and pending_text and not is_chapter_cover(pending_text):
            item_id, chapter_no, item_no = parsed
            current = BodyItem(
                item_id=item_id,
                chapter_no=chapter_no,
                section_no=item_no,
                title=pending_text,
                page=block["page"],
            )
            items.append(current)
            pending_text = None
            pending_chapter_no = None
            block_state = {"block": None, "level3": None}
            continue

        release_pending()
        pending_text = text

    release_pending()
    for item in items:
        if not item.blocks:
            warnings.append(f"{item.item_id}에서 본문 내용을 찾지 못했습니다.")
    return items, chapters, warnings


# 현재 열려 있는 묶음을 돌려주고 없으면 제목 없는 선행 묶음을 만든다.
# 첫 ❍보다 앞에 놓인 본문(예: 3-1 정부기구도)이 여기에 담긴다.
def _current_block(item: BodyItem, state: dict) -> ContentBlock:
    block = state.get("block")
    if block is None:
        block = ContentBlock()
        item.blocks.append(block)
        state["block"] = block
    return block


# 항목 안의 문단 하나를 제목·단위·연락처·주석·본문 줄 중 하나로 분류해 반영한다.
def _absorb_paragraph(item: BodyItem, text: str, state: dict, publication_year: int) -> None:
    if item.base_date is None and not item.blocks:
        base_date = normalize_base_date(text, publication_year)
        if base_date:
            item.base_date = base_date
            return

    level3 = RE_LEVEL3.match(text)
    if level3:
        block = ContentBlock(level3_title=clean_text(level3.group("title")))
        item.blocks.append(block)
        state["block"] = block
        state["level3"] = block
        return

    level4 = RE_LEVEL4.match(text)
    if level4:
        # 직전 ❍ 묶음이 제목만 있고 내용이 없으면 이 <> 표들을 묶기 위한 상위 제목이다.
        # 이미 자기 내용을 가진 ❍ 뒤에 오는 <>는 그 아래가 아니라 나란히 놓인 다른 표다.
        # (예: "❍ 2024년 모금현황" 아래 <기부 추이>는 하위, "❍ 추진방향"의 설명 뒤에
        #  나오는 <지구촌 새마을운동 현황>은 별개)
        parent = state.get("level3")
        inherits = parent is not None and not parent.has_content()
        block = ContentBlock(
            level3_title=parent.level3_title if inherits else None,
            level4_title=clean_text(level4.group("title")),
        )
        item.blocks.append(block)
        state["block"] = block
        return

    unit = RE_UNIT_LINE.match(text)
    if unit:
        _current_block(item, state).unit = clean_text(unit.group("unit"))
        return

    if is_contact_line(text):
        for contact in parse_contact_line(text):
            _append_unique_contact(item.contacts, contact)
        return

    if RE_NOTE.match(text):
        _current_block(item, state).notes.append(text)
        return

    _current_block(item, state).lines.append(text)


# 표를 현재 묶음에 붙인다. 글상자는 표가 아니라 본문이므로 줄로 풀어 본문처럼 분류한다.
# 담당 부서 줄이나 주석이 글상자 안에 들어가는 경우가 있어 줄마다 다시 분류해야 한다.
def _absorb_table(item: BodyItem, table: dict, state: dict, publication_year: int) -> None:
    if not is_text_box(table):
        _current_block(item, state).tables.append(table)
        return
    lines = text_box_lines(table)
    if is_colophon(lines):
        return
    for line in lines:
        _absorb_paragraph(item, line, state, publication_year)


# 같은 담당자가 쪽 분할로 두 번 실리는 것을 막는다.
def _append_unique_contact(contacts: list[dict], candidate: dict) -> None:
    signature = (candidate.get("dept"), candidate.get("officer"), candidate.get("phone"))
    for contact in contacts:
        if (contact.get("dept"), contact.get("officer"), contact.get("phone")) == signature:
            return
    contacts.append(candidate)


# 묶음이 통계 행이 될 자격이 있는지 본다. 내용이 없어도 제목이 수치를 담으면 남긴다.
def block_is_loadable(block: ContentBlock) -> bool:
    if block.has_content():
        return True
    return title_carries_data(block.level4_title or block.level3_title)


# 검색과 표시에 쓸 제목을 만든다. 항목 제목과 묶음 제목을 겹치지 않게 잇는다.
#
# 주요통계집의 묶음 제목은 "개요", "기부 추이"처럼 항목 이름 없이는 뜻이 통하지 않는 것이
# 많다. 반대로 "서해 5도 관광객"처럼 이미 항목 이름을 품은 것도 있어 그대로 이으면 말이
# 겹친다. 그래서 묶음 제목이 항목 이름을 이미 품고 있으면 묶음 제목만 쓴다.
def compose_title(section_title: str, leaf_title: str | None) -> str:
    if not leaf_title:
        return section_title
    if _normalized(section_title) in _normalized(leaf_title):
        return leaf_title
    return f"{section_title} {leaf_title}"


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


# 한 묶음을 적재 포맷의 통계 단위 dict로 만든다.
def block_to_unit(
    item: BodyItem,
    block: ContentBlock,
    ref_id: str,
    ordinal: int,
    chapter_title: str | None,
) -> dict:
    heading = block.level4_title or block.level3_title
    lines = list(block.lines)
    # ❍ 제목은 "서해 5도 인구 : 8,151명"처럼 제목 자리에 값을 적는다. 표가 따로 없으면
    # 그 값이 본문에서만 사라지지 않도록 제목 줄도 표에 남긴다. <>는 표 제목일 뿐이다.
    if not block.tables and block.level4_title is None and title_carries_data(heading):
        lines = [heading, *lines]

    tables: list[dict] = []
    if lines:
        tables.append(text_table_record(len(tables) + 1, heading, lines))
    for table in block.tables:
        tables.append(table_record(table, len(tables) + 1, heading))

    return {
        "ref_id": ref_id,
        "ordinal": ordinal,
        "chapter_no": item.chapter_no,
        "section_no": item.section_no,
        "level3_no": None,
        "level4_no": None,
        "chapter": chapter_title,
        "section": item.title,
        "level3_title": block.level3_title,
        "level3_title_en": None,
        "level4_title": block.level4_title,
        "level4_title_en": None,
        "title_ko": compose_title(item.title, heading),
        "title_en": None,
        "unit": block.unit,
        "base_date": item.base_date,
        "page_start": item.page,
        "tables": tables,
        "footnotes": [
            {"seq": index, "note_no": None, "content": note}
            for index, note in enumerate(block.notes, start=1)
        ],
        "contacts": [dict(contact) for contact in item.contacts],
    }


# 한 항목의 묶음들을 통계 단위 목록으로 편다.
# 묶음이 둘 이상이면 ref_id에 순번을 붙여 발간물 안에서 유일하게 만든다.
def item_to_units(
    item: BodyItem,
    ordinal_start: int,
    chapter_title: str | None,
) -> list[dict]:
    loadable = [block for block in item.blocks if block_is_loadable(block)]
    if not loadable:
        return []
    units: list[dict] = []
    for index, block in enumerate(loadable, start=1):
        ref_id = item.item_id if len(loadable) == 1 else f"{item.item_id}-{index}"
        units.append(
            block_to_unit(item, block, ref_id, ordinal_start + len(units), chapter_title)
        )
    return units


# 항목 번호가 장 안에서 이어지는지 확인해 잘못 잡은 경계를 검수 목록으로 남긴다.
def check_item_sequence(items: list[BodyItem]) -> list[str]:
    warnings: list[str] = []
    previous: dict[int | None, int] = {}
    for item in items:
        expected = previous.get(item.chapter_no, 0) + 1
        if item.section_no != expected:
            warnings.append(
                f"{item.item_id}의 항목 번호가 이어지지 않습니다(직전 번호 기준 {expected} 예상)."
            )
        previous[item.chapter_no] = item.section_no or expected
    return warnings


# 본문 항목을 앞머리 목차와 대조해 빠지거나 남는 항목을 검수용으로 정리한다.
def reconcile_with_toc(items: list[BodyItem], entries: dict[str, dict]) -> dict:
    body_ids = {item.item_id for item in items}
    ref_mismatch = [
        {
            "ref_id": item.item_id,
            "body_title": item.title,
            "toc_title": entries[item.item_id]["title"],
        }
        for item in items
        if item.item_id in entries
        and _normalized(entries[item.item_id]["title"]) != _normalized(item.title)
    ]
    return {
        "toc_ref_mismatch": ref_mismatch,
        "toc_only_entries": [
            {"toc_ref_id": ref_id, "title_ko": entry["title"], "toc_page": entry["page"]}
            for ref_id, entry in entries.items()
            if ref_id not in body_ids
        ],
        "body_only_entries": [
            {"ref_id": item.item_id, "title_ko": item.title}
            for item in items
            if item.item_id not in entries
        ],
    }


# "참고-1"처럼 장 번호를 적지 않는 항목이 속할 장 번호를 고른다.
# 참고자료 장은 언제나 마지막 장이지만, 이름으로 먼저 찾아야 장이 하나 더 붙어도 흔들리지 않는다.
def reference_chapter_no(chapters: dict[int, str]) -> int | None:
    for number, title in sorted(chapters.items()):
        if "참고" in (title or ""):
            return number
    return max(chapters) if chapters else None


# 발간물 제목을 만든다. 같은 해에 두 판이 나오므로 반기 표기를 반드시 넣는다.
def default_title(publication_year: int, publication_period: str) -> str:
    label = publication_period_label(publication_period)
    return f"{publication_year}년 {label} 주요통계집".replace("  ", " ").strip()


# 주요통계집 HWPX를 통계연보와 같은 적재 포맷의 발간물·통계 JSON으로 만든다.
def parse_major_statistics(
    hwpx_path: str,
    publication_year: int,
    publication_period: str | None = None,
    publication_title: str | None = None,
    publication_no: str | None = None,
    publication_kind: str | None = MAJOR_STATISTICS_KIND,
) -> dict:
    period = normalize_publication_period(publication_period)
    blocks = list(iter_body_blocks(hwpx_path))
    toc_chapters, toc_entries = parse_table_of_contents(blocks)
    items, body_chapters, warnings = split_body_items(blocks, publication_year, toc_chapters)
    if not items:
        raise ValueError("주요통계집 본문에서 항목 번호를 찾지 못했습니다.")

    chapters = {**toc_chapters, **body_chapters}
    fallback_chapter_no = reference_chapter_no(chapters)
    for item in items:
        if item.chapter_no is None:
            item.chapter_no = fallback_chapter_no
        entry = toc_entries.get(item.item_id)
        if entry:
            item.page = entry["page"]

    units: list[dict] = []
    for item in items:
        units.extend(
            item_to_units(item, len(units) + 1, chapters.get(item.chapter_no))
        )
    warnings.extend(check_item_sequence(items))

    publication = {
        "publication_kind": normalize_publication_kind(publication_kind),
        "publication_period": period,
        "year": publication_year,
        "pub_no": publication_no or None,
        "title": publication_title or default_title(publication_year, period),
        "page_count": max((block["page"] for block in blocks), default=None),
    }
    return {
        "publication": publication,
        "metadata": {
            "source": os.path.abspath(hwpx_path),
            "parser": "admin/backend/services/load_major_statistics.py",
            "method": (
                "본문 항목 번호(n-m / 참고-m)로 항목을 자르고, 항목 안의 ❍ 표제를 3계층, "
                "<> 표제를 4계층으로 삼아 묶음마다 통계 행을 만든다. 표가 없는 묶음은 본문 "
                "줄을 한 컬럼짜리 표로 만들어 table_md와 body에 담는다."
            ),
            "toc_entries": len(toc_entries),
            "body_items": len(items),
            "chapters": chapters,
            "warnings": sorted(set(warnings)),
        },
        "checks": {**check_units(units), "items": len(items)},
        "toc_reconciliation": reconcile_with_toc(items, toc_entries),
        "statistics": units,
    }
