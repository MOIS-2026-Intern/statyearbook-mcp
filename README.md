# 행정안전통계연보 챗봇

통계연보를 검색하고 원자료 표와 Vega-Lite 시각화를 제공하는 서비스입니다.

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

새 연보는 관리자 화면 또는 다음 명령으로 적재합니다.

```bash
python -m admin ingest data/통계연보.hwpx --year 2026 --embedding bge-m3
```

기본 적재, 두 임베딩과 검증은 하나의 DB 트랜잭션으로 실행되어 중간 실패 시 모두 롤백됩니다.

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
