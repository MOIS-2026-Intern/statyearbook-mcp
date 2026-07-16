-- BGE-M3 전환과 반복 가능한 임베딩 작업 관리를 위한 스키마.
-- 기존 OpenAI 벡터는 롤백을 위해 embedding_legacy_1536에 보존한다.

CREATE TABLE embedding_profiles (
    profile_key    TEXT PRIMARY KEY,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    revision       TEXT NOT NULL DEFAULT '',
    dimension      INT NOT NULL CHECK (dimension > 0),
    max_length     INT NOT NULL CHECK (max_length > 0),
    content_version TEXT NOT NULL,
    normalized     BOOLEAN NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE embedding_jobs (
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

DROP INDEX idx_stat_embed;

ALTER TABLE statistics
    RENAME COLUMN embedding TO embedding_legacy_1536;

ALTER TABLE statistics
    ADD COLUMN embedding vector(1024),
    ADD COLUMN embedding_profile_key TEXT
        REFERENCES embedding_profiles(profile_key);

COMMENT ON COLUMN statistics.embedding_legacy_1536 IS
    'BGE-M3 전환 전 text-embedding-3-small 벡터. 전환 검증 후 별도 migration으로 제거 가능';
COMMENT ON COLUMN statistics.embedding IS
    '현재 활성 임베딩. embedding_profile_key와 항상 함께 갱신';

CREATE INDEX idx_stat_embedding_profile
    ON statistics(embedding_profile_key);
CREATE INDEX idx_embedding_jobs_started
    ON embedding_jobs(started_at DESC);
CREATE INDEX idx_stat_embed
    ON statistics USING hnsw (embedding vector_cosine_ops);
