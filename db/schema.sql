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

CREATE TABLE IF NOT EXISTS table_search_chunks (
    chunk_id              BIGSERIAL PRIMARY KEY,
    table_id              BIGINT NOT NULL REFERENCES stat_tables(table_id) ON DELETE CASCADE,
    chunk_no              INT NOT NULL CHECK (chunk_no > 0),
    chunk_kind            TEXT NOT NULL CHECK (chunk_kind IN ('headers', 'labels')),
    search_labels         JSONB NOT NULL DEFAULT '[]'::jsonb,
    search_text           TEXT NOT NULL,
    search_doc            TSVECTOR NOT NULL,
    embedding             vector(1024),
    embedding_profile_key TEXT REFERENCES embedding_profiles(profile_key),
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_publications_unique_year
    ON publications(year);
CREATE INDEX IF NOT EXISTS idx_stat_year
    ON statistics(year);
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
