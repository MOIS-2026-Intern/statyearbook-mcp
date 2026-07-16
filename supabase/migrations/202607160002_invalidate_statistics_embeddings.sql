-- 임베딩 원문이 변경되면 기존 벡터를 자동으로 무효화한다.
-- 다음 증분 embedding job이 해당 행만 다시 처리한다.

CREATE OR REPLACE FUNCTION invalidate_statistics_embedding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.title_ko IS DISTINCT FROM OLD.title_ko
       OR NEW.title_en IS DISTINCT FROM OLD.title_en
       OR NEW.chapter IS DISTINCT FROM OLD.chapter
       OR NEW.section IS DISTINCT FROM OLD.section THEN
        NEW.embedding := NULL;
        NEW.embedding_profile_key := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_invalidate_statistics_embedding
BEFORE UPDATE OF title_ko, title_en, chapter, section ON statistics
FOR EACH ROW
EXECUTE FUNCTION invalidate_statistics_embedding();
