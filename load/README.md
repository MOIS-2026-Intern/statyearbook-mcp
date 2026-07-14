# DB 적재 방법

행정안전통계연보 HWPX 원본을 파싱해 PostgreSQL에 적재하고, 검색용 임베딩까지 생성하는 순서입니다.

## 스크립트 역할

1. `parse_hwpx_yearbook.py`가 HWPX 원본을 직접 읽어서 DB 적재용 JSON과 검수용 Markdown을 생성합니다.
   - HWPX ZIP 내부의 `Contents/section*.xml`을 문서 순서대로 순회합니다.
   - `hp:cellAddr`, `hp:cellSpan`으로 병합 셀 원본을 `body.cells`에 보존합니다.
   - 병합 헤더를 최하위 컬럼명으로 펼쳐 `body.records`와 `table_md`를 생성합니다.
2. `load_to_postgres.py`가 `parsed_yearbook.json`에 따라 DB에 적재하거나 DML SQL을 생성합니다.
3. `embed_statistics.py`가 통계 제목 임베딩을 생성해 DB에 저장합니다.

## 터미널 사용 순서

### 1. PostgreSQL DB와 스키마를 준비합니다

처음 한 번만 DB를 만들고 마이그레이션을 실행합니다.

```bash
createdb statyearbook_mcp
psql -d statyearbook_mcp -f supabase/migrations/202607140001_initial_schema.sql
```

### 2. HWPX 원본을 파싱합니다

```bash
python load/parse_hwpx_yearbook.py data/통계연보.hwpx \
  --json-out load/output/parsed_yearbook.json \
  --md-out load/output/parsed_yearbook.md
```

생성 결과는 다음 두 파일입니다.

- `load/output/parsed_yearbook.json`: DB 적재용 구조화 데이터
- `load/output/parsed_yearbook.md`: 사람이 검수하기 위한 Markdown

필요하면 터미널에서 검수용 Markdown을 확인합니다.

```bash
less load/output/parsed_yearbook.md
```

### 3. PostgreSQL에 적재합니다

```bash
python load/load_to_postgres.py load/output/parsed_yearbook.json
```

이 명령은 기본적으로 다음 작업을 함께 수행합니다.

- `STATYEARBOOK_DSN`이 있으면 실제 DB에 적재합니다.
- `db/seeds/load_all.sql`에 재적재용 SQL을 생성합니다.
- 적재 시 기존 테이블 데이터를 `TRUNCATE ... RESTART IDENTITY CASCADE`로 비우고 다시 넣습니다.

DSN을 명령에서 직접 지정하려면 다음처럼 실행합니다.

```bash
python load/load_to_postgres.py load/output/parsed_yearbook.json \
  --dsn "postgresql://USER:PASSWORD@localhost:5432/statyearbook_mcp"
```

### 4. 임베딩을 생성합니다

```bash
python load/embed_statistics.py
```

기본 실행은 `embedding IS NULL`인 통계만 처리합니다. 이미 생성된 임베딩까지 모두 다시 만들려면 다음처럼 실행합니다.

```bash
python load/embed_statistics.py --all
```

### 5. 적재 결과를 확인합니다

```bash
psql -d statyearbook_mcp -c "SELECT COUNT(*) FROM publications;"
psql -d statyearbook_mcp -c "SELECT COUNT(*) FROM statistics;"
psql -d statyearbook_mcp -c "SELECT COUNT(*) FROM stat_tables;"
```

## SQL 파일만 생성하기

실 DB 적재 없이 DML만 만들려면 `--no-db`를 사용합니다.

```bash
python load/load_to_postgres.py load/output/parsed_yearbook.json \
  --no-db \
  --emit-sql db/seeds/load_all.sql
```

생성된 SQL을 나중에 직접 적용하려면 다음처럼 실행합니다.

```bash
psql -d statyearbook_mcp -f db/seeds/load_all.sql
```
