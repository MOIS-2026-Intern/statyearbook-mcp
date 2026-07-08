#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import base64
import json
import os
import re

import ijson

RE_REFID    = re.compile(r'^(\d+-\d+-\d+(?:-\d+)?)\s+(.*)', re.S)   # '1-1-1-2 제목...'
RE_PHONE    = re.compile(r'0\d{1,2}[-)]\s?\d{3,4}[-]\d{4}')
RE_BASEDATE = re.compile(r'\(?\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\s*기준\s*\)?')
RE_UNIT     = re.compile(r'\(?\s*단위\s*[:：]\s*([^)\n]+?)\s*\)')
RE_URL      = re.compile(r'((?:https?://|www\.)[^\s()]+)')
RE_NOTE_NO  = re.compile(r'^#?\s*(주\d*\))')
RE_EN_SPLIT = re.compile(r'\s(?=[A-Z][a-z])')   # 한글제목 뒤 영문제목 경계


# 전화번호를 표준 하이픈 형식으로 정리한다.
def norm_phone(s: str) -> str | None:
    m = RE_PHONE.search(s)
    if not m:
        return None
    p = re.sub(r'[)\s]', '-', m.group(0))
    p = re.sub(r'-+', '-', p).strip('-')
    return p


# 제목 셀 텍스트에서 한글 제목과 영문 제목을 분리한다.
def split_title(text: str):
    text = text.strip()
    if '\n' in text:
        ko, en = text.split('\n', 1)
        return ko.strip(), en.strip().replace('\n', ' ') or None
    m = RE_EN_SPLIT.search(text)
    if m:
        return text[:m.start()].strip(), text[m.start():].strip()
    return text, None


# 표 셀 텍스트를 정리한다.
def cell_text(cell: dict) -> str:
    return (cell.get('text') or '').replace('\n', ' ').strip()


# 표 셀 병합 크기를 읽는다.
def cell_span(cell: dict) -> tuple[int, int]:
    col_span = cell.get('colSpan', 1) or 1
    row_span = cell.get('rowSpan', 1) or 1
    return col_span, row_span


# 병합 셀의 텍스트를 그리드에 채운다.
def fill_grid(grid: list, row: int, col: int, col_span: int, row_span: int, text: str) -> None:
    n_rows = len(grid)
    n_cols = len(grid[0]) if grid else 0
    for dr in range(row_span):
        for dc in range(col_span):
            rr, cc = row + dr, col + dc
            if rr < n_rows and cc < n_cols:
                grid[rr][cc] = text


# 비어 있는 셀을 빈 문자열로 바꾼다.
def normalize_grid(grid: list) -> list:
    return [[value if value is not None else '' for value in row] for row in grid]


# 병합 셀을 반영해 2D 텍스트 그리드로 펼친다.
def cells_to_grid(table: dict):
    n_rows, n_cols = table.get('rows', 0), table.get('cols', 0)
    grid = [[None] * n_cols for _ in range(n_rows)]
    for r, row in enumerate(table.get('cells', [])):
        c = 0
        for cell in row:
            while c < n_cols and grid[r][c] is not None:
                c += 1
            if c >= n_cols:
                break
            txt = cell_text(cell)
            cs, rs = cell_span(cell)
            fill_grid(grid, r, c, cs, rs, txt)
            c += cs
    return normalize_grid(grid)


# 전 컬럼 병합된 캡션 행 번호를 찾는다.
def caption_row_idx(table: dict):
    n_cols = table.get('cols', 0)
    skip = set()
    for r, row in enumerate(table.get('cells', [])):
        if row and (row[0].get('colSpan', 1) or 1) >= n_cols:
            skip.add(r)
    return skip


# 마크다운 표 셀 특수문자를 이스케이프한다.
def markdown_cell(text: str) -> str:
    return text.replace('|', '\\|')


# 마크다운 표 행을 만든다.
def markdown_row(cells: list[str]) -> str:
    values = " | ".join(markdown_cell(cell) for cell in cells)
    return f"| {values} |"


# 마크다운 헤더 구분 행을 만든다.
def markdown_separator(width: int) -> str:
    return markdown_row(['---'] * width)


# 2D 그리드를 마크다운 표로 바꾼다.
def grid_to_markdown(grid, skip=None):
    skip = skip or set()
    rows = [row for i, row in enumerate(grid) if i not in skip]
    if not rows:
        return ''
    out = [markdown_row(rows[0]), markdown_separator(len(rows[0]))]
    for row in rows[1:]:
        out.append(markdown_row(row))
    return '\n'.join(out)


# 표 상단에서 기준일, 단위, 캡션을 추출한다.
def extract_meta_from_table(table: dict):
    texts = []
    for row in table.get('cells', [])[:2]:
        for cell in row:
            t = (cell.get('text') or '').strip()
            if t:
                texts.append(t)
    blob = ' '.join(texts)
    bd = RE_BASEDATE.search(blob)
    un = RE_UNIT.search(blob)
    base_date = bd.group(1).replace(' ', '') if bd else None
    unit = un.group(1).strip() if un else None
    caption = texts[0] if texts else None
    return base_date, unit, caption


# 연락처 문단에서 출처 영역을 분리한다.
def split_source(text: str) -> tuple[str, str | None, str | None]:
    if '/' not in text:
        return text, None, None
    left, right = text.split('/', 1)
    url_match = RE_URL.search(right)
    source_url = url_match.group(1) if url_match else None
    source_system = re.sub(r'\(.*?\)', '', right).strip() or None
    return left.strip(), source_system, source_url


# 연락처 문단에서 부서와 담당자를 분리한다.
def split_officer(text: str, phone: str | None) -> tuple[str | None, str | None]:
    who = RE_PHONE.split(text)[0].strip() if phone else text
    who = who.strip(' ()')
    if not who:
        return None, None
    parts = who.split()
    dept = parts[0]
    officer = ' '.join(parts[1:]) or None
    return dept, officer


# 연락처 문단을 DB 저장용 필드로 분해한다.
def parse_contact(text: str):
    t = text.lstrip('*').strip()
    phone = norm_phone(t)
    t, source_system, source_url = split_source(t)
    dept, officer = split_officer(t, phone)
    return {'dept': dept, 'officer': officer, 'phone': phone,
            'source_system': source_system, 'source_url': source_url}


# 제목표이면 ref_id와 제목 문자열을 반환한다.
def is_title_table(block):
    if block.get('type') != 'table':
        return None
    tb = block['table']
    if tb.get('cols') == 1 and tb.get('cells') and tb['cells'][0]:
        txt = (tb['cells'][0][0].get('text') or '').strip()
        m = RE_REFID.match(txt)
        if m:
            return m.group(1), m.group(2)
    return None


# 기본 발간물 메타데이터를 만든다.
def default_publication() -> dict:
    return {
        'year': 2025,
        'pub_no': None,
        'title': '2025 행정안전통계연보',
        'page_count': None,
    }


# JSON 메타데이터에서 페이지 수를 읽는다.
def read_page_count(json_path: str):
    with open(json_path, 'rb') as f:
        try:
            return next(ijson.items(f, 'metadata.pageCount'))
        except StopIteration:
            return None


# ref_id에서 장/절 번호를 읽는다.
def ref_numbers(ref_id: str) -> tuple[int | None, int | None]:
    nums = ref_id.split('-')
    chapter_no = int(nums[0]) if len(nums) > 0 else None
    section_no = int(nums[1]) if len(nums) > 1 else None
    return chapter_no, section_no


# 제목표 정보로 새 통계 단위를 만든다.
def make_unit(ref_id: str, raw_title: str, page_start: int | None) -> dict:
    title_ko, title_en = split_title(raw_title)
    chapter_no, section_no = ref_numbers(ref_id)
    return {
        'ref_id': ref_id,
        'chapter_no': chapter_no,
        'section_no': section_no,
        'title_ko': title_ko,
        'title_en': title_en,
        'unit': None,
        'base_date': None,
        'page_start': page_start,
        'tables': [],
        'footnotes': [],
        'contacts': [],
        'images': [],
    }


# 데이터표에서 통계 단위 메타데이터를 보강한다.
def apply_table_meta(unit: dict, base_date: str | None, unit_name: str | None) -> None:
    if base_date and not unit['base_date']:
        unit['base_date'] = base_date
    if unit_name and not unit['unit']:
        unit['unit'] = unit_name


# 표 블록을 저장용 레코드로 만든다.
def table_record(table: dict, seq: int, caption: str | None) -> dict:
    grid = cells_to_grid(table)
    return {
        'seq': seq,
        'caption': caption,
        'n_rows': table.get('rows'),
        'n_cols': table.get('cols'),
        'body': table,
        'table_md': grid_to_markdown(grid, caption_row_idx(table)),
    }


# 현재 통계 단위에 데이터표를 추가한다.
def add_table(unit: dict, table: dict) -> None:
    base_date, unit_name, caption = extract_meta_from_table(table)
    apply_table_meta(unit, base_date, unit_name)
    seq = len(unit['tables']) + 1
    unit['tables'].append(table_record(table, seq, caption))


# 문단이 주석 시작인지 확인한다.
def is_note_text(text: str) -> bool:
    return text.startswith('#주') or bool(RE_NOTE_NO.match(text))


# 주석 문단을 저장용 레코드로 만든다.
def note_record(text: str, seq: int) -> dict:
    match = RE_NOTE_NO.match(text)
    content = re.sub(r'^#', '', text).strip()
    return {
        'seq': seq,
        'note_no': match.group(1) if match else None,
        'content': content,
    }


# 현재 통계 단위에 문단 내용을 반영한다.
def handle_paragraph(unit: dict, text: str, pending_note: dict | None) -> dict | None:
    if not text:
        return pending_note
    if is_note_text(text):
        note = note_record(text, len(unit['footnotes']) + 1)
        unit['footnotes'].append(note)
        return note
    if text.startswith('-') and pending_note:
        pending_note['content'] = f"{pending_note['content']} {text}"
        return pending_note
    if text.startswith('*'):
        contact = parse_contact(text)
        if contact['phone'] or contact['dept']:
            unit['contacts'].append(contact)
    return None


# 이미지 base64 데이터를 파일로 저장한다.
def save_image(image_dir: str | None, filename: str, data: str | None) -> str | None:
    if not image_dir or not data or len(data) <= 100:
        return None
    os.makedirs(image_dir, exist_ok=True)
    uri = os.path.join(image_dir, filename)
    try:
        with open(uri, 'wb') as image_file:
            image_file.write(base64.b64decode(data))
    except Exception:
        return None
    return uri


# 현재 통계 단위에 이미지 블록을 추가한다.
def add_image(unit: dict, block: dict, image_dir: str | None, image_seq: int) -> None:
    filename = block.get('text') or f'image_{image_seq:03d}.jpg'
    uri = save_image(image_dir, filename, block.get('imageData'))
    unit['images'].append({
        'filename': filename,
        'page': block.get('pageNumber'),
        'uri': uri,
        'caption': None,
    })


# 데이터표가 있는 통계 단위만 출력 대상에 추가한다.
def append_unit(units: list[dict], unit: dict | None) -> None:
    if unit and unit['tables']:
        units.append(unit)


# JSON blocks 스트림을 통계 단위 리스트로 변환한다.
def parse_units(json_path: str, image_dir: str | None = None) -> list[dict]:
    units = []
    cur = None
    pending_note = None
    img_seq = 0

    with open(json_path, 'rb') as f:
        for block in ijson.items(f, 'blocks.item'):
            title = is_title_table(block)
            if title:
                append_unit(units, cur)
                ref_id, raw_title = title
                cur = make_unit(ref_id, raw_title, block.get('pageNumber'))
                pending_note = None
                continue

            if cur is None:
                continue

            block_type = block.get('type')
            if block_type == 'table':
                add_table(cur, block['table'])
                pending_note = None
            elif block_type == 'paragraph':
                text = (block.get('text') or '').strip()
                pending_note = handle_paragraph(cur, text, pending_note)
            elif block_type == 'image':
                img_seq += 1
                add_image(cur, block, image_dir, img_seq)

    append_unit(units, cur)
    return units


# 연보 JSON을 DB 적재용 구조로 변환한다.
def parse(json_path: str, image_dir: str | None = None) -> dict:
    pub = default_publication()
    pub['page_count'] = read_page_count(json_path)
    units = parse_units(json_path, image_dir)

    return {'publication': pub, 'statistics': units}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument('json_path')
    ap.add_argument('-o', '--out', default='load/output/parsed_yearbook.json')
    ap.add_argument('--image-dir', default=None,
                    help='지정 시 이미지 base64를 파일로 저장')
    return ap


def write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def count_items(stats: list[dict], key: str) -> int:
    return sum(len(unit[key]) for unit in stats)


def print_summary(result: dict, out_path: str) -> None:
    stats = result['statistics']
    print(f'통계 단위 : {len(stats)}')
    print(f"  표      : {count_items(stats, 'tables')}")
    print(f"  주석    : {count_items(stats, 'footnotes')}")
    print(f"  연락처  : {count_items(stats, 'contacts')}")
    print(f"  이미지  : {count_items(stats, 'images')}")
    print(f'-> {out_path}')


def main() -> None:
    args = build_parser().parse_args()
    result = parse(args.json_path, args.image_dir)
    write_json(args.out, result)
    print_summary(result, args.out)


if __name__ == '__main__':
    main()
