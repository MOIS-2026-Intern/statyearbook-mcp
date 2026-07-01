#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_yearbook.py
행정안전통계연보 파싱 JSON(blocks)을 -> DB 적재용 구조로 변환한다.

입력 : 통계연보2.json  (top keys: success, fileType, markdown, blocks, metadata, outline, images)
       -> 실제로 쓰는 건 blocks (표/문단/제목/이미지) 와 metadata.
출력 : parsed_yearbook.json  (publications 1건 + statistics 단위 리스트)

통계 "단위(unit)" 구성 규칙 (blocks 를 순서대로 훑으며 그룹핑):
  - 제목표(title table)  : cols==1 이고 첫 셀이 '1-1-1-2 ...' 계층 ID로 시작 -> 새 단위 시작
  - 데이터표(data table) : 그 외 표 -> 현재 단위의 stat_tables 로 귀속 (셀 구조 그대로 JSONB)
  - '#주' 문단           : 현재 단위의 footnote (뒤따르는 '-' 문단은 같은 주석에 이어붙임)
  - '*' 문단             : 현재 단위의 contact (부서/이름/전화/출처/URL 파싱)
  - image 블록           : 현재 단위의 이미지
  * 데이터표가 하나도 없는 단위(절 그룹 제목 등)는 최종 출력에서 제외.
"""
import ijson, json, re, argparse, os, base64

# ── 정규식 ────────────────────────────────────────────────
RE_REFID    = re.compile(r'^(\d+-\d+-\d+(?:-\d+)?)\s+(.*)', re.S)   # '1-1-1-2 제목...'
RE_PHONE    = re.compile(r'0\d{1,2}[-)]\s?\d{3,4}[-]\d{4}')
RE_BASEDATE = re.compile(r'\(?\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\s*기준\s*\)?')
RE_UNIT     = re.compile(r'\(?\s*단위\s*[:：]\s*([^)\n]+?)\s*\)')
RE_URL      = re.compile(r'((?:https?://|www\.)[^\s()]+)')
RE_NOTE_NO  = re.compile(r'^#?\s*(주\d*\))')
RE_EN_SPLIT = re.compile(r'\s(?=[A-Z][a-z])')   # 한글제목 뒤 영문제목 경계


def norm_phone(s: str) -> str:
    m = RE_PHONE.search(s)
    if not m:
        return None
    p = re.sub(r'[)\s]', '-', m.group(0))
    p = re.sub(r'-+', '-', p).strip('-')
    return p


def split_title(text: str):
    """제목 셀 텍스트에서 (한글제목, 영문제목) 분리."""
    text = text.strip()
    if '\n' in text:                       # 줄바꿈이 있으면 첫 줄=ko, 나머지=en
        ko, en = text.split('\n', 1)
        return ko.strip(), en.strip().replace('\n', ' ') or None
    m = RE_EN_SPLIT.search(text)           # 없으면 첫 영문 대문자 경계로 분리
    if m:
        return text[:m.start()].strip(), text[m.start():].strip()
    return text, None


def cells_to_grid(table: dict):
    """colSpan/rowSpan을 반영해 rows x cols 2D 텍스트 그리드로 펼친다(병합셀은 텍스트 반복)."""
    n_rows, n_cols = table.get('rows', 0), table.get('cols', 0)
    grid = [[None] * n_cols for _ in range(n_rows)]
    for r, row in enumerate(table.get('cells', [])):
        c = 0
        for cell in row:
            while c < n_cols and grid[r][c] is not None:
                c += 1
            if c >= n_cols:
                break
            txt = (cell.get('text') or '').replace('\n', ' ').strip()
            cs, rs = cell.get('colSpan', 1) or 1, cell.get('rowSpan', 1) or 1
            for dr in range(rs):
                for dc in range(cs):
                    rr, cc = r + dr, c + dc
                    if rr < n_rows and cc < n_cols:
                        grid[rr][cc] = txt
            c += cs
    return [[(v if v is not None else '') for v in row] for row in grid]


def caption_row_idx(table: dict):
    """전 컬럼 병합된 캡션/구분 행(단일셀 colSpan==cols)의 인덱스 집합."""
    n_cols = table.get('cols', 0)
    skip = set()
    for r, row in enumerate(table.get('cells', [])):
        if row and (row[0].get('colSpan', 1) or 1) >= n_cols:
            skip.add(r)
    return skip


def grid_to_markdown(grid, skip=None):
    """2D 그리드 -> GitHub 마크다운 표(첫 행 헤더). 캡션 행(skip)은 제외."""
    skip = skip or set()
    rows = [row for i, row in enumerate(grid) if i not in skip]
    if not rows:
        return ''
    esc = lambda s: s.replace('|', '\\|')
    out = ['| ' + ' | '.join(esc(c) for c in rows[0]) + ' |',
           '| ' + ' | '.join('---' for _ in rows[0]) + ' |']
    for row in rows[1:]:
        out.append('| ' + ' | '.join(esc(c) for c in row) + ' |')
    return '\n'.join(out)


def extract_meta_from_table(table: dict):
    """데이터표 상단 셀들에서 base_date / unit / caption 추출."""
    texts = []
    for row in table.get('cells', [])[:2]:      # 상단 1~2행만 스캔
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


def parse_contact(text: str):
    """'* OO과 주무관 OOO (044-205-OOOO) / 정부조직관리정보시스템(www.org.go.kr)'"""
    t = text.lstrip('*').strip()
    phone = norm_phone(t)
    source_system = source_url = None
    if '/' in t:
        left, right = t.split('/', 1)
        u = RE_URL.search(right)
        if u:
            source_url = u.group(1)
        source_system = re.sub(r'\(.*?\)', '', right).strip() or None
        t = left.strip()
    # phone 앞부분 = 부서 + 담당자
    who = RE_PHONE.split(t)[0].strip() if phone else t
    who = who.strip(' ()')
    dept = officer = None
    if who:
        parts = who.split()
        dept = parts[0]
        officer = ' '.join(parts[1:]) or None
    return {'dept': dept, 'officer': officer, 'phone': phone,
            'source_system': source_system, 'source_url': source_url}


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


def parse(json_path: str, image_dir: str = None):
    pub = {'year': 2025, 'pub_no': None, 'title': '2025 행정안전통계연보',
           'page_count': None}

    units = []
    cur = None                 # 현재 통계 단위
    pending_note = None        # 이어붙일 주석

    def flush():
        nonlocal cur, pending_note
        if cur and cur['tables']:          # 데이터표 있는 단위만 채택
            units.append(cur)
        cur, pending_note = None, None

    # metadata (page_count) 먼저
    with open(json_path, 'rb') as f:
        try:
            pub['page_count'] = next(ijson.items(f, 'metadata.pageCount'))
        except StopIteration:
            pass

    with open(json_path, 'rb') as f:
        img_seq = 0
        for b in ijson.items(f, 'blocks.item'):
            btype = b.get('type')

            # 1) 제목표 -> 새 단위
            title = is_title_table(b)
            if title:
                flush()
                ref_id, raw = title
                ko, en = split_title(raw)
                nums = ref_id.split('-')
                cur = {
                    'ref_id': ref_id,
                    'chapter_no': int(nums[0]) if len(nums) > 0 else None,
                    'section_no': int(nums[1]) if len(nums) > 1 else None,
                    'title_ko': ko, 'title_en': en,
                    'unit': None, 'base_date': None,
                    'page_start': b.get('pageNumber'),
                    'tables': [], 'footnotes': [], 'contacts': [], 'images': [],
                }
                continue

            if cur is None:
                continue       # 첫 제목표 이전(표지/목차)은 스킵

            # 2) 데이터표
            if btype == 'table':
                tb = b['table']
                base_date, unit, caption = extract_meta_from_table(tb)
                if base_date and not cur['base_date']:
                    cur['base_date'] = base_date
                if unit and not cur['unit']:
                    cur['unit'] = unit
                grid = cells_to_grid(tb)
                cur['tables'].append({
                    'seq': len(cur['tables']) + 1,
                    'caption': caption,
                    'n_rows': tb.get('rows'), 'n_cols': tb.get('cols'),
                    'body': tb,                       # 파싱값(cells+span) 그대로
                    'table_md': grid_to_markdown(grid, caption_row_idx(tb)),
                })
                pending_note = None
                continue

            # 3) 문단: 주석 / 연락처 / 주석 이어붙이기
            if btype == 'paragraph':
                txt = (b.get('text') or '').strip()
                if not txt:
                    continue
                if txt.startswith('#주') or RE_NOTE_NO.match(txt):
                    m = RE_NOTE_NO.match(txt)
                    note = {'seq': len(cur['footnotes']) + 1,
                            'note_no': m.group(1) if m else None,
                            'content': re.sub(r'^#', '', txt).strip()}
                    cur['footnotes'].append(note)
                    pending_note = note
                elif txt.startswith('-') and pending_note:
                    pending_note['content'] += ' ' + txt
                elif txt.startswith('*'):
                    c = parse_contact(txt)
                    if c['phone'] or c['dept']:
                        cur['contacts'].append(c)
                    pending_note = None
                else:
                    pending_note = None
                continue

            # 4) 이미지
            if btype == 'image':
                img_seq += 1
                fname = b.get('text') or f'image_{img_seq:03d}.jpg'
                uri = None
                data = b.get('imageData')
                if image_dir and data and len(data) > 100:
                    os.makedirs(image_dir, exist_ok=True)
                    uri = os.path.join(image_dir, fname)
                    try:
                        with open(uri, 'wb') as im:
                            im.write(base64.b64decode(data))
                    except Exception:
                        uri = None
                cur['images'].append({'filename': fname,
                                      'page': b.get('pageNumber'), 'uri': uri,
                                      'caption': None})
                continue
        flush()

    return {'publication': pub, 'statistics': units}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('json_path')
    ap.add_argument('-o', '--out', default='parsed_yearbook.json')
    ap.add_argument('--image-dir', default=None,
                    help='지정 시 이미지 base64를 파일로 저장')
    args = ap.parse_args()

    result = parse(args.json_path, args.image_dir)
    # parsed.json 은 body(원본 셀)를 포함하되 base64는 이미 제외됨
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    stats = result['statistics']
    n_tbl = sum(len(u['tables']) for u in stats)
    n_note = sum(len(u['footnotes']) for u in stats)
    n_con = sum(len(u['contacts']) for u in stats)
    n_img = sum(len(u['images']) for u in stats)
    print(f'통계 단위 : {len(stats)}')
    print(f'  표      : {n_tbl}')
    print(f'  주석    : {n_note}')
    print(f'  연락처  : {n_con}')
    print(f'  이미지  : {n_img}')
    print(f'-> {args.out}')
