-- 연도별 연보는 하나만 허용해 누적 적재와 교체 작업의 자연키를 보장한다.
CREATE UNIQUE INDEX idx_publications_unique_year ON publications(year);
