-- ============================================================
-- schema.sql : 행정안전통계연보 챗봇용 스키마 (PostgreSQL + pgvector)
-- ============================================================
-- 매 실행마다 public 스키마를 통째로 비우고 재생성 → 완전 초기화(멱등)
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

-- 스키마를 다시 만든 뒤에 확장 생성(순서 중요: 스키마를 지우면 그 안의 확장도 지워짐)
CREATE EXTENSION IF NOT EXISTS vector;
-- (선택) 한국어 부분일치 키워드 검색용. 설치돼 있으면 아래 인덱스 주석 해제
-- CREATE EXTENSION IF NOT EXISTS pg_bigm;


-- ① 연보(발간물)
CREATE TABLE publications (
    pub_id     SERIAL PRIMARY KEY,
    year       INT  NOT NULL,
    pub_no     TEXT,
    title      TEXT NOT NULL,
    page_count INT
);

-- ② 통계 단위 : 검색이 일어나는 층(모든 표가 동일 구조로 통일)
CREATE TABLE statistics (
    stat_id     BIGSERIAL PRIMARY KEY,
    pub_id      INT REFERENCES publications(pub_id),
    year        INT  NOT NULL,
    ref_id      TEXT,            -- '1-1-1-2' 계층 ID
    chapter_no  INT,
    section_no  INT,
    chapter     TEXT,
    section     TEXT,
    title_ko    TEXT NOT NULL,
    title_en    TEXT,
    unit        TEXT,            -- '개', '명' ...
    base_date   TEXT,            -- '2024.12.31.'
    page_start  INT,
    search_doc  tsvector,
    embedding   vector(1536)     -- 임베딩 모델 차원에 맞게 조정
);

-- ③ 표 본문 : 표마다 다른 층(통일하지 않고 JSONB로 보존)
CREATE TABLE stat_tables (
    table_id  BIGSERIAL PRIMARY KEY,
    stat_id   BIGINT REFERENCES statistics(stat_id) ON DELETE CASCADE,
    seq       INT,
    caption   TEXT,
    n_rows    INT,
    n_cols    INT,
    body      JSONB,            -- {"rows","cols","cells":[[{text,colSpan,rowSpan}]],"hasHeader"}
    table_md  TEXT              -- LLM에 먹일 마크다운 렌더본
);

-- ④ 주석
CREATE TABLE footnotes (
    note_id   BIGSERIAL PRIMARY KEY,
    stat_id   BIGINT REFERENCES statistics(stat_id) ON DELETE CASCADE,
    seq       INT,
    note_no   TEXT,
    content   TEXT
);

-- ⑤ 담당 연락처(+ 자료 출처)
CREATE TABLE contacts (
    contact_id    BIGSERIAL PRIMARY KEY,
    stat_id       BIGINT REFERENCES statistics(stat_id) ON DELETE CASCADE,
    dept          TEXT,
    officer       TEXT,
    phone         TEXT,
    source_system TEXT,
    source_url    TEXT
);

-- ⑥ (선택) 이미지 : 조직도 등. base64는 파일로 저장하고 경로만 보관
CREATE TABLE statistic_images (
    image_id  BIGSERIAL PRIMARY KEY,
    stat_id   BIGINT REFERENCES statistics(stat_id) ON DELETE CASCADE,
    filename  TEXT,
    page      INT,
    uri       TEXT,
    caption   TEXT
);

-- ── 인덱스 ──────────────────────────────────────────────
CREATE INDEX idx_stat_year   ON statistics(year);
CREATE INDEX idx_stat_refid  ON statistics(ref_id);
CREATE INDEX idx_stat_search ON statistics USING gin(search_doc);
CREATE INDEX idx_stat_embed  ON statistics USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_tables_body ON stat_tables USING gin(body);
CREATE INDEX idx_tables_stat ON stat_tables(stat_id);
CREATE INDEX idx_notes_stat  ON footnotes(stat_id);
CREATE INDEX idx_contacts_stat ON contacts(stat_id);
-- (pg_bigm 사용 시)
-- CREATE INDEX idx_title_bigm ON statistics USING gin (title_ko gin_bigm_ops);
