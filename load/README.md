# DB 적재 방법

행정안전통계연보 HWPX 원본을 파싱해 PostgreSQL에 적재하고, 검색용 임베딩까지 생성하는 순서입니다.
일상적인 관리자 작업에는 아래 개별 스크립트 대신 통합 명령을 사용합니다.

```bash
python -m admin ingest data/2026_통계연보.hwpx --year 2026
```

이 문서의 개별 명령은 장애 분석이나 특정 단계만 다시 실행할 때 사용합니다.

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
psql -d statyearbook_mcp -f supabase/migrations/202607160001_embedding_management.sql
psql -d statyearbook_mcp -f supabase/migrations/202607160002_invalidate_statistics_embeddings.sql
psql -d statyearbook_mcp -f supabase/migrations/202607160003_unique_publication_year.sql
```

### 2. HWPX 원본을 파싱합니다

```bash
python load/parse_hwpx_yearbook.py data/통계연보.hwpx \
  --year 2026 \
  --title "2026 행정안전통계연보" \
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
- `db/seeds/load_yearbook.sql`에 이관 가능한 누적 적재 SQL을 생성합니다.
- 기본 `reject` 모드는 같은 연도가 이미 있으면 기존 데이터를 건드리지 않고 중단합니다.
- `--mode replace`는 선택한 연도의 기존 데이터만 교체하며 다른 연도는 보존합니다.

DSN을 명령에서 직접 지정하려면 다음처럼 실행합니다.

```bash
python load/load_to_postgres.py load/output/parsed_yearbook.json \
  --dsn "postgresql://USER:PASSWORD@localhost:5432/statyearbook_mcp"
```

### 4. 임베딩을 생성합니다

적재와 검색 질의는 `.env`의 동일한 `STATYEARBOOK_EMBED_*` 설정을 사용합니다.
기존 OpenAI 임베딩을 계속 사용할 때는 다음과 같이 설정합니다.

```dotenv
STATYEARBOOK_EMBED_PROVIDER=openai
STATYEARBOOK_EMBED_MODEL=text-embedding-3-small
STATYEARBOOK_EMBED_DIMENSION=1536
```

```bash
python load/embed_statistics.py
```

기본 실행은 임베딩이 없거나 현재 model profile과 다른 통계만 처리합니다. 이미 생성된
임베딩까지 모두 다시 만들려면 다음처럼 실행합니다.

```bash
python load/embed_statistics.py --all
```

### BGE-M3 오프라인 모델 준비

인터넷에 연결된 빌드 환경에서 고정된 모델 revision을 다운로드합니다. 모델 파일은
Git에 커밋하지 않으며 `models/bge-m3` 디렉터리를 이미지나 읽기 전용 볼륨에 포함합니다.

```bash
python scripts/download_embedding_model.py
```

운영 환경과 동일하게 네트워크 사용을 차단한 상태에서 모델 로딩, 1024차원 출력,
L2 정규화를 검증합니다.

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  python scripts/verify_embedding_model.py
```

검증이 끝난 뒤 `.env`를 다음과 같이 변경합니다.

```dotenv
STATYEARBOOK_EMBED_PROVIDER=local
STATYEARBOOK_EMBED_MODEL=models/bge-m3
STATYEARBOOK_EMBED_DIMENSION=1024
STATYEARBOOK_EMBED_REVISION=5617a9f61b028005a4858fdac845db406aefb181
STATYEARBOOK_EMBED_DEVICE=cpu
STATYEARBOOK_EMBED_BATCH_SIZE=16
STATYEARBOOK_EMBED_MAX_LENGTH=512
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

`embed_statistics.py`는 설정된 차원과 `statistics.embedding` 컬럼의 차원이 다르면
DB를 수정하지 않고 중단합니다. BGE-M3 전환 migration은 활성 컬럼을 `vector(1024)`로
만들고 기존 OpenAI 벡터를 `embedding_legacy_1536`에 보존합니다. 이후 차원이 다른
모델로 바꿀 때도 먼저 별도의 pgvector 차원 전환 migration을 적용해야 합니다.

### 반복 운영과 신규 통계표 임베딩

현재 적용 현황과 최근 실행 이력을 확인합니다.

```bash
python load/embed_statistics.py --status
```

신규 적재 후 처리할 행만 미리 확인합니다.

```bash
python load/embed_statistics.py --dry-run
```

기본 실행은 다음 행만 증분 처리합니다.

- `embedding`이 없는 신규 통계표
- 현재 환경의 모델/revision/차원/텍스트 버전과 다른 profile로 처리된 통계표
- 제목·장·절이 수정되어 DB trigger가 기존 embedding을 무효화한 통계표

```bash
python load/embed_statistics.py
```

같은 profile의 기존 행까지 강제로 다시 만들 때만 `--all`을 사용합니다.

```bash
python load/embed_statistics.py --all
```

각 실행은 `embedding_jobs`에 대상 수, 완료 수, 상태와 오류를 기록합니다. 실행 시점의
최대 `stat_id`를 경계로 잡기 때문에 처리 도중 들어온 데이터는 다음 증분 실행에서
안전하게 처리됩니다. 동시에 두 작업이 실행되지 않도록 PostgreSQL advisory lock도
사용합니다.

구현은 다음 세 경계로 분리되어 있습니다.

- `embedding_pipeline.py`: provider와 데이터 소스를 조합하는 공통 batch runner
- `statistics_embedding_source.py`: 통계표 조회, 임베딩 텍스트 구성, 결과 저장
- `embed_statistics.py`: 관리자 CLI와 환경변수 구성

향후 다른 DB 테이블을 임베딩하려면 `EmbeddingSource` 프로토콜을 구현하는 source
adapter를 추가하고 같은 `EmbeddingRunner`를 재사용합니다.

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
  --emit-sql db/seeds/load_yearbook.sql
```

생성된 SQL을 나중에 직접 적용하려면 다음처럼 실행합니다.

```bash
psql -d statyearbook_mcp -f db/seeds/load_yearbook.sql
```
