-- 행정안전통계연보 최종 PostgreSQL 스키마.
-- 로컬 PostgreSQL과 운영 Supabase PostgreSQL에서 동일하게 사용한다.
-- 반복 실행해도 기존 데이터는 삭제하지 않는다.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS publications (
    pub_id      SERIAL PRIMARY KEY,
    year        INT NOT NULL,
    pub_no      TEXT,
    title       TEXT NOT NULL,
    page_count  INT
);

CREATE TABLE IF NOT EXISTS embedding_profiles (
    profile_key     TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    revision        TEXT NOT NULL DEFAULT '',
    dimension       INT NOT NULL CHECK (dimension > 0),
    max_length      INT NOT NULL CHECK (max_length > 0),
    content_version TEXT NOT NULL,
    normalized      BOOLEAN NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS statistics (
    stat_id               BIGSERIAL PRIMARY KEY,
    pub_id                INT REFERENCES publications(pub_id),
    year                  INT NOT NULL,
    ref_id                TEXT,
    -- 발간물 안에서의 본문 등장 순서다. 쪽 번호가 같아도 순서가 흔들리지 않게 한다.
    ordinal               INT,
    chapter_no            INT,
    section_no            INT,
    level3_no             INT,
    level4_no             INT,
    chapter               TEXT,
    section               TEXT,
    level3_title          TEXT,
    level4_title          TEXT,
    title_ko              TEXT NOT NULL,
    title_en              TEXT,
    unit                  TEXT,
    base_date             TEXT,
    page_start            INT,
    search_doc            TSVECTOR,
    embedding             vector(1024),
    embedding_profile_key TEXT REFERENCES embedding_profiles(profile_key)
);

CREATE TABLE IF NOT EXISTS stat_tables (
    table_id  BIGSERIAL PRIMARY KEY,
    stat_id   BIGINT REFERENCES statistics(stat_id) ON DELETE CASCADE,
    seq       INT,
    caption   TEXT,
    n_rows    INT,
    n_cols    INT,
    body      JSONB,
    table_md  TEXT
);

-- 표 단위 청크(headers·labels)와 통계 단위 청크(notes)를 한 테이블에 함께 담는다.
-- 주석은 표가 아니라 통계에 달리므로 stat_id만 채우고 table_id는 비운다. 같은 테이블에
-- 두면 검색이 이미 실행하는 전문·벡터 조회에 주석이 그대로 후보로 들어와 SQL이 늘지 않는다.
CREATE TABLE IF NOT EXISTS table_search_chunks (
    chunk_id              BIGSERIAL PRIMARY KEY,
    stat_id               BIGINT NOT NULL REFERENCES statistics(stat_id) ON DELETE CASCADE,
    table_id              BIGINT REFERENCES stat_tables(table_id) ON DELETE CASCADE,
    chunk_no              INT NOT NULL CHECK (chunk_no > 0),
    chunk_kind            TEXT NOT NULL CHECK (chunk_kind IN ('headers', 'labels', 'notes')),
    search_labels         JSONB NOT NULL DEFAULT '[]'::jsonb,
    search_text           TEXT NOT NULL,
    search_doc            TSVECTOR NOT NULL,
    embedding             vector(1024),
    embedding_profile_key TEXT REFERENCES embedding_profiles(profile_key),
    CONSTRAINT table_search_chunks_scope_check
        CHECK ((chunk_kind = 'notes') = (table_id IS NULL)),
    UNIQUE (table_id, chunk_kind, chunk_no)
);

CREATE TABLE IF NOT EXISTS footnotes (
    note_id  BIGSERIAL PRIMARY KEY,
    stat_id  BIGINT REFERENCES statistics(stat_id) ON DELETE CASCADE,
    seq      INT,
    note_no  TEXT,
    content  TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    contact_id    BIGSERIAL PRIMARY KEY,
    stat_id       BIGINT REFERENCES statistics(stat_id) ON DELETE CASCADE,
    dept          TEXT,
    officer       TEXT,
    phone         TEXT,
    source_system TEXT,
    source_url    TEXT
);

CREATE TABLE IF NOT EXISTS embedding_jobs (
    job_id          BIGSERIAL PRIMARY KEY,
    source_name     TEXT NOT NULL,
    profile_key     TEXT NOT NULL REFERENCES embedding_profiles(profile_key),
    status          TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    force_reembed   BOOLEAN NOT NULL DEFAULT FALSE,
    target_count    INT NOT NULL DEFAULT 0 CHECK (target_count >= 0),
    processed_count INT NOT NULL DEFAULT 0 CHECK (processed_count >= 0),
    max_source_id   BIGINT NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

-- 이미 만들어진 DB에도 statistics.ordinal을 더한다. CREATE TABLE IF NOT EXISTS만으로는
-- 기존 테이블에 컬럼이 생기지 않는다.
ALTER TABLE statistics ADD COLUMN IF NOT EXISTS ordinal INT;

-- 이미 만들어진 DB의 table_search_chunks를 통계 단위 주석 청크까지 담도록 넓힌다.
-- 기존 headers·labels 행의 search_text는 건드리지 않으므로 이미 만든 벡터는 그대로 쓴다.
ALTER TABLE table_search_chunks ADD COLUMN IF NOT EXISTS stat_id BIGINT;
UPDATE table_search_chunks c
   SET stat_id = t.stat_id
  FROM stat_tables t
 WHERE t.table_id = c.table_id
   AND c.stat_id IS NULL;
ALTER TABLE table_search_chunks ALTER COLUMN stat_id SET NOT NULL;
ALTER TABLE table_search_chunks ALTER COLUMN table_id DROP NOT NULL;

DO $statyearbook_chunk_scope$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'table_search_chunks'::regclass
           AND conname = 'table_search_chunks_stat_id_fkey'
    ) THEN
        ALTER TABLE table_search_chunks
            ADD CONSTRAINT table_search_chunks_stat_id_fkey
            FOREIGN KEY (stat_id) REFERENCES statistics(stat_id) ON DELETE CASCADE;
    END IF;
END
$statyearbook_chunk_scope$;

-- CHECK 제약은 IF NOT EXISTS를 지원하지 않으므로 지우고 다시 만들어 재실행을 견딘다.
ALTER TABLE table_search_chunks
    DROP CONSTRAINT IF EXISTS table_search_chunks_chunk_kind_check;
ALTER TABLE table_search_chunks
    ADD CONSTRAINT table_search_chunks_chunk_kind_check
    CHECK (chunk_kind IN ('headers', 'labels', 'notes'));
ALTER TABLE table_search_chunks
    DROP CONSTRAINT IF EXISTS table_search_chunks_scope_check;
ALTER TABLE table_search_chunks
    ADD CONSTRAINT table_search_chunks_scope_check
    CHECK ((chunk_kind = 'notes') = (table_id IS NULL));

-- pub_id+ref_id 유일 색인을 만들기 전에 남아 있는 중복을 사람이 알아볼 수 있게 알린다.
-- 중복이 있으면 해당 연도를 replace 모드로 다시 적재해야 한다.
DO $statyearbook_dup_guard$
DECLARE
    v_dup TEXT;
BEGIN
    SELECT string_agg(DISTINCT year || ':' || ref_id, ', ')
      INTO v_dup
      FROM (
          SELECT year, ref_id
            FROM statistics
           WHERE ref_id IS NOT NULL
           GROUP BY pub_id, year, ref_id
          HAVING COUNT(*) > 1
      ) AS duplicated;
    IF v_dup IS NOT NULL THEN
        RAISE EXCEPTION
            'statistics에 같은 발간물의 중복 ref_id가 있어 유일 색인을 만들 수 없습니다: %. '
            '해당 연도를 replace 모드로 다시 적재하십시오.', v_dup;
    END IF;
END
$statyearbook_dup_guard$;

-- 한 연도에 발간물은 하나라는 전제를 강제한다. 적재 스크립트와 통계 검색의 발간판 병합이
-- 이 전제에 기대므로, 발간물 종류를 늘리려면 발간물 구분 컬럼을 먼저 추가하고
-- app/tools/search_statistics.py의 LATEST_EDITIONS_CTE를 함께 고쳐야 한다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_publications_unique_year
    ON publications(year);
-- 한 발간물 안에서 표 번호는 유일하다. 파서가 같은 표를 두 번 넣거나 번호를 밀어
-- 쓰는 사고를 적재 단계에서 곧바로 막는다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_statistics_unique_pub_ref
    ON statistics(pub_id, ref_id);
CREATE INDEX IF NOT EXISTS idx_stat_year
    ON statistics(year);
CREATE INDEX IF NOT EXISTS idx_stat_ordinal
    ON statistics(pub_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_stat_refid
    ON statistics(ref_id);
CREATE INDEX IF NOT EXISTS idx_stat_search
    ON statistics USING gin(search_doc);
CREATE INDEX IF NOT EXISTS idx_stat_embedding_profile
    ON statistics(embedding_profile_key);
CREATE INDEX IF NOT EXISTS idx_stat_embed
    ON statistics USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_tables_body
    ON stat_tables USING gin(body);
CREATE INDEX IF NOT EXISTS idx_tables_stat
    ON stat_tables(stat_id);
CREATE INDEX IF NOT EXISTS idx_table_search_chunks_table
    ON table_search_chunks(table_id);
CREATE INDEX IF NOT EXISTS idx_table_search_chunks_stat
    ON table_search_chunks(stat_id);
-- 주석 청크는 table_id가 비어 있어 UNIQUE (table_id, chunk_kind, chunk_no)로는 중복이 막히지
-- 않는다. NULL은 서로 다른 값으로 취급되기 때문이다. 통계 단위로 따로 유일성을 건다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_table_search_chunks_notes_unique
    ON table_search_chunks(stat_id, chunk_no)
    WHERE chunk_kind = 'notes';
CREATE INDEX IF NOT EXISTS idx_table_search_chunks_doc
    ON table_search_chunks USING gin(search_doc);
CREATE INDEX IF NOT EXISTS idx_table_search_chunks_profile
    ON table_search_chunks(embedding_profile_key);
CREATE INDEX IF NOT EXISTS idx_table_search_chunks_embedding
    ON table_search_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_notes_stat
    ON footnotes(stat_id);
CREATE INDEX IF NOT EXISTS idx_contacts_stat
    ON contacts(stat_id);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_started
    ON embedding_jobs(started_at DESC);

CREATE OR REPLACE FUNCTION invalidate_statistics_embedding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.title_ko IS DISTINCT FROM OLD.title_ko
       OR NEW.title_en IS DISTINCT FROM OLD.title_en
       OR NEW.chapter IS DISTINCT FROM OLD.chapter
       OR NEW.section IS DISTINCT FROM OLD.section
       OR NEW.level3_title IS DISTINCT FROM OLD.level3_title
       OR NEW.level4_title IS DISTINCT FROM OLD.level4_title THEN
        NEW.embedding := NULL;
        NEW.embedding_profile_key := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_invalidate_statistics_embedding
BEFORE UPDATE OF title_ko, title_en, chapter, section,
                 level3_title, level4_title ON statistics
FOR EACH ROW
EXECUTE FUNCTION invalidate_statistics_embedding();

CREATE OR REPLACE FUNCTION invalidate_table_search_chunk_embedding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.search_text IS DISTINCT FROM OLD.search_text THEN
        NEW.search_doc := to_tsvector('simple', NEW.search_text);
        NEW.embedding := NULL;
        NEW.embedding_profile_key := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_invalidate_table_search_chunk_embedding
BEFORE UPDATE OF search_text ON table_search_chunks
FOR EACH ROW
EXECUTE FUNCTION invalidate_table_search_chunk_embedding();

COMMIT;
