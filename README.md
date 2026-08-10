# 행정안전통계연보 챗봇

통계연보를 검색하고 원자료 표와 Vega-Lite 시각화를 제공하는 서비스입니다.



https://github.com/user-attachments/assets/20630c68-0cc8-4a16-8c34-6256d2f9e189



## 서비스 구조

| 디렉터리 | 배포 단위 |
|---|---|
| `admin/` | 연보 파싱·적재·임베딩 관리자 |
| `app/` | 통계 도구를 제공하는 HTTP MCP 서버 |
| `backend/` | 채팅 모델과 MCP를 연결하는 REST API |
| `frontend/` | React 채팅 UI |
| `db/` | pgvector PostgreSQL schema |

`utils/`에는 서비스 공통 프로필 로더와 순수 임베딩·벡터 유틸리티만 있습니다. `data/`, `models/`, `docs/`는 서비스 코드가 아니며 각 서비스 이미지에 복사되지 않습니다.

## 환경 프로필

모든 Python 서비스는 `APP_PROFILE=local|test|main`을 사용합니다. 기본값은 `local`, CI는 `test`, Docker 배포 이미지는 `main`입니다. 각 서비스의 `profiles/<profile>.env` 기본값보다 운영체제·배포 환경변수와 서비스별 `.env.<profile>`이 우선합니다.

frontend는 Vite의 `development|test|production` 모드를 사용합니다. `test`는 저장소의 `.env.test`로 로컬 test backend를 바라보고, `production`은 빌드 인자로 URL을 받습니다.

```bash
cp app/.env.example app/.env.local
cp backend/.env.example backend/.env.local
cp admin/.env.example admin/.env.local
cp frontend/.env.example frontend/.env.development.local
```

`main` 배포에는 서비스별로 다음 값을 secret 또는 배포 환경변수로 주입하세요.

- app: `STATYEARBOOK_APP_DSN`, `STATYEARBOOK_APP_HF_TOKEN`
- backend: `STATYEARBOOK_BACKEND_MCP_URL`, `STATYEARBOOK_BACKEND_CORS_ORIGINS`, 선택한 공급자의 `STATYEARBOOK_BACKEND_OPENAI_API_KEY` 또는 `STATYEARBOOK_BACKEND_BIZROUTER_API_KEY`
- admin: `STATYEARBOOK_ADMIN_DSN`, `STATYEARBOOK_ADMIN_API_TOKEN`, BGE-M3 모델 볼륨
- frontend: 이미지 빌드 인자 `VITE_BACKEND_BASE_URL`
- db: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

BGE-M3는 Git과 이미지에 포함하지 않습니다. local/test의 app과 로컬 적재를 담당하는 admin은 호스트의 같은 모델 artifact를 사용합니다. 운영 app은 기본적으로 Hugging Face Inference API에서 같은 `BAAI/bge-m3` revision의 query embedding만 생성하므로 모델 볼륨이 필요하지 않습니다. `STATYEARBOOK_APP_EMBED_PROVIDER=local|huggingface`로 실행 provider를 선택하며, Hugging Face를 선택하면 `STATYEARBOOK_APP_HF_TOKEN`을 secret으로 주입해야 합니다. 두 provider는 1024차원·정규화·고정 revision과 같은 DB embedding profile key를 사용합니다.

admin의 작업 이력과 업로드 작업공간은 각각 `/service/admin/state`, `/service/admin/workspaces`에 있으므로 운영에서는 두 경로에 영속 볼륨을 연결해야 합니다.

db 이미지는 **빈 PostgreSQL 데이터 볼륨을 처음 초기화할 때만** `db/schema.sql`을 자동 적용합니다. 이미 생성된 DB는 배포 전에 다음 명령으로 스키마를 갱신하세요. 스키마는 반복 적용해도 기존 데이터를 삭제하지 않습니다.

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema.sql
```

## 로컬 실행

```bash
python -m pip install -r app/requirements.txt -r backend/requirements.txt -r admin/requirements.txt
psql -d statyearbook_mcp -v ON_ERROR_STOP=1 -f db/schema.sql
python -m app             # http://127.0.0.1:8001/mcp
python -m backend         # http://127.0.0.1:8000
python -m admin serve     # http://127.0.0.1:8100
cd frontend && npm ci && npm run dev
```

## 서비스 로그

backend와 app(MCP server)의 기본 로그 레벨은 `DEBUG`입니다. 배포 환경에서
`STATYEARBOOK_BACKEND_LOG_LEVEL`과 `STATYEARBOOK_APP_LOG_LEVEL`을 각각
`DEBUG|INFO|WARNING|ERROR|CRITICAL`로 변경할 수 있습니다. 성공한 `/health` 요청은
기록하지 않고 실패한 health 요청만 ERROR로 기록합니다.

로그 메시지는 검색 가능한 `event=...` 형식입니다. 성공 로그는 동작마다 하나만
남기며 주요 병목 태그는 `event=model.call`, `event=mcp.call`, `event=tool.call`,
`event=embedding`, `event=sql`, `event=http`입니다. 완료·실패 로그에는
`duration_ms`가 포함됩니다. 반복되는 MCP transport HTTP, `httpx`, SSE payload 로그는
숨기며 SQL은 파라미터와 본문을 읽기 쉽게 줄바꿈해 표시합니다. 긴 벡터 값은 자동
축약됩니다.

채팅 요청이 끝나면 `event=chat.pipeline` 로그에 `mcp_connect_ms`,
`mcp_discovery_ms`, `model_ms`, `mcp_tools_ms`와 가장 오래 걸린 `bottleneck`이
기록됩니다. 프런트엔드는 `POST /api/chat/stream`의 NDJSON 진행 이벤트를 받아
MCP 연결, 도구 확인, 모델 분석, 도구 호출, 결과 검토 상태를 표시합니다. 기존
`POST /api/chat` JSON API도 호환성을 위해 유지합니다. MCP 도구 사양은 기본 300초
동안 재사용하며 `STATYEARBOOK_BACKEND_MCP_TOOL_CACHE_TTL_SECONDS=0`으로 끌 수
있습니다. backend는 종료 신호 뒤 진행 중인 요청을 기본 5초까지만 기다리며,
`STATYEARBOOK_BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS`로 조정할 수 있습니다.

새 연보는 관리자 화면 또는 다음 명령으로 적재합니다.

```bash
python -m admin ingest data/통계연보.hwpx --year 2026 --embedding bge-m3
```

기본 적재, 두 임베딩과 검증은 하나의 DB 트랜잭션으로 실행되어 중간 실패 시 모두 롤백됩니다.

DB에 넣기 전에 파싱 결과만 확인하려면 `build-sql`로 검수 문서와 적재 SQL만 만듭니다.

```bash
python -m admin build-sql data/2026통계연보.hwpx --year 2026 --out admin/workspaces/rebuild-2026
```

### 목차 계층 복원 규칙

표 번호(`ref_id`)와 장·절·3계층·4계층 제목은 **본문 표제 표**를 정본으로 삼습니다.
앞머리 목차는 장·절 이름과 교차검증에만 씁니다. 2026년 연보 목차에는 본문에서
빠진 항목(`4-2-1 지역주도형 청년일자리 사업 실적`, `3-1-2 전자정부 수출실적조사 결과`,
둘 다 쪽 번호가 `?`)이 남아 있어 그 뒤 leaf 번호가 본문보다 하나씩 밀려 있습니다.
목차를 정본으로 쓰면 `기부금품 모집등록`이 `4-2-10`과 `4-2-11`에 두 번 들어가는 식으로
제목과 번호가 어긋납니다.

본문과 목차가 다른 지점은 `yearbook_review.md`의 `본문과 목차의 번호가 다른 항목`,
`목차에만 있는 항목`, `본문에만 있는 항목`에 정리되므로 적재 전에 확인하십시오.
같은 발간물 안에서 `ref_id`가 겹치면 SQL 생성 단계와 `statistics(pub_id, ref_id)`
유일 색인이 각각 적재를 막습니다.

## 검증과 이미지 빌드

```bash
APP_PROFILE=test python -m unittest discover -s tests -v
cd frontend && npm run build:test

docker build -f admin/Dockerfile -t statyearbook-admin .
docker build -f app/Dockerfile -t statyearbook-app .
docker build -f backend/Dockerfile -t statyearbook-backend .
docker build -f frontend/Dockerfile -t statyearbook-frontend --build-arg VITE_BACKEND_BASE_URL=https://backend.example frontend
docker build -f db/Dockerfile -t statyearbook-db db
```
