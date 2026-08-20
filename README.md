# 행정안전통계연보 챗봇

통계연보를 검색하고 원자료 표와 Vega-Lite 시각화를 제공하는 서비스입니다.



https://github.com/user-attachments/assets/20630c68-0cc8-4a16-8c34-6256d2f9e189



## 서비스 구조

| 디렉터리 | 배포 단위 |
|---|---|
| `admin/` | 연보 파싱·적재·임베딩 관리자 |
| `app/` | 통계 도구를 제공하는 MCP 서버 |
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

## MCP 클라이언트에 직접 연결

app은 backend·frontend 없이 MCP 클라이언트에 단독으로 붙일 수 있습니다. `--transport`
(또는 `STATYEARBOOK_APP_TRANSPORT`)로 transport를 고르며 기본값은 backend가 사용하는
`streamable-http`입니다.

```bash
python -m app                      # http://127.0.0.1:8001/mcp
python -m app --transport stdio    # 클라이언트가 프로세스를 직접 실행
```

Claude Desktop처럼 서버 프로세스를 직접 띄우는 클라이언트는 `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`)에 stdio 실행 명령을 등록합니다.

```json
{
  "mcpServers": {
    "statyearbook": {
      "command": "/절대경로/statyearbook-mcp/.venv/bin/python",
      "args": ["-m", "app", "--transport", "stdio"],
      "cwd": "/절대경로/statyearbook-mcp",
      "env": { "PYTHONPATH": "/절대경로/statyearbook-mcp" }
    }
  }
}
```

`PYTHONPATH`에 저장소 루트를 반드시 넣으세요. Claude Desktop은 `cwd`를 적용하지 않고
클라이언트마다 작업 디렉터리가 다르므로, 이것이 없으면 `No module named app`으로 바로
종료합니다. local 프로필의 `STATYEARBOOK_APP_EMBED_MODEL=models/bge-m3` 같은 상대 경로
모델은 app이 저장소 루트 기준으로 해석하므로 작업 디렉터리와 무관합니다.

DB와 임베딩 provider 준비는 transport와 무관하게 동일합니다. stdio에서는 stdout이
JSON-RPC 채널이므로 배너와 서비스 로그는 stderr로만 나갑니다. 클라이언트가 서버를
띄우지 못하면 그 로그부터 확인하세요(macOS Claude Desktop은
`~/Library/Logs/Claude/mcp-server-<이름>.log`).

이미 `streamable-http`로 떠 있는 서버에 붙이려면 클라이언트에서 stdio↔HTTP 프록시를
쓰면 됩니다.

```json
{
  "mcpServers": {
    "statyearbook": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://127.0.0.1:8001/mcp", "--allow-http"]
    }
  }
}
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

입력창의 모델 드롭다운은 backend의 `GET /api/models`에서 허용 목록을 읽습니다.
`STATYEARBOOK_BACKEND_CHAT_MODELS`에 BizRouter 모델 ID를 쉼표로 추가하면 새 모델이
드롭다운에 나타나고, `STATYEARBOOK_BACKEND_CHAT_MODEL`은 그 목록 안에서 기본값을
정합니다. 채팅 요청의 `model`은 이 허용 목록으로 검증되며 모델별 gateway 연결 풀로
분기됩니다.

답변을 생성하는 동안 전송 버튼은 멈춤 버튼으로 바뀝니다. 멈춤은 스트림 연결을 끊고,
backend는 그 자리에서 모델 추론과 MCP 도구 호출을 취소한 뒤 세션과 요청 상태를 버립니다
(`event=chat.stream.stopped`, `event=chat.pipeline outcome=stopped`). 중단된 턴은 화면과
localStorage에 `사용자에 의해 응답이 중단되었습니다`로만 남고, 받다 만 본문과 MCP trace는
저장하지 않습니다. 답을 받지 못한 질문과 앞선 대화·trace는 그대로 남아 다음 질문에 함께
전달되므로, 중단한 뒤 이어서 물으면 모델이 앞 질문을 알고 답합니다. 화면용 기록인 중단
안내만 모델 입력에서 빠집니다.

## 조회 범위

입력창의 버튼으로 **전체**(기본값), **통계연보**, **주요통계집** 가운데 어디에서 찾을지 고릅니다.

전체는 `search_statistics`를 `publication_kind=all`로 호출해 두 발간물을 각각의 최신 발간판부터
한 번에 검색하고, 발간물마다 상위 후보를 번갈아 남깁니다. `limit`은 발간물마다 적용되어 두
발간물에서 각각 최대 `limit`개가 돌아옵니다. 그래서 한쪽 발간물에만 실린 통계도 후보에 남고,
발간물별로 고를 표가 남습니다.

**두 발간물에 모두 관련 표가 있으면 둘 다 읽어 하나의 답변으로 엮습니다.** 주요통계집은 현황과
개요를 한 시점 기준으로 정리해 두었고 통계연보는 같은 주제를 연도별 추이와 세부 분류로 담고
있으므로, 개요·최신 현황은 주요통계집에서, 추이·세부 내역은 통계연보에서 가져옵니다. 후보와 표
조회 결과에는 `publication_kind`와 `publication_label`(예: `2025년 하반기 주요통계집`)이 함께
오므로 표와 수치마다 어느 발간물의 어느 판인지 밝히고, 두 발간물의 값이 다르면 기준일과 함께
양쪽을 모두 적습니다. 반기는 주요통계집에만 있어 `publication_period` 조건은 주요통계집 검색에만
적용됩니다.

통계연보 또는 주요통계집을 고르면 그 발간물의 최신 발간판만 검색하고, 다른 발간물의 내용은
답변에 쓰지 않습니다. 범위마다 모델 지시문도 달라집니다(`backend/prompts.py`의
`PUBLICATION_SCOPE_PROMPTS`).

한 발간판 안에서만 집계·비교하는 `analyze_publications`와 `compare_publications`는 전체 범위에서
`all`을 받지 않습니다. 이때는 모델이 사용자가 말한 발간물을 전달하고, 말하지 않으면 통계연보를
사용합니다.

범위를 바꾸면 그 전에 주고받은 대화는 모델 입력에서 빠집니다. 전체 범위에서 본 주요통계집 표를
기억한 채 통계연보로 좁히면 통계연보에 없는 수치를 그대로 옮겨 적기 때문입니다. 화면의 대화
기록은 그대로 남고 모델에 넘기는 이력만 지금 범위의 마지막 구간으로 잘립니다.

새 연보는 관리자 화면 또는 다음 명령으로 적재합니다.

```bash
python -m admin ingest data/통계연보.hwpx --year 2026 --embedding bge-m3
```

기본 적재, 두 임베딩과 검증은 하나의 DB 트랜잭션으로 실행되어 중간 실패 시 모두 롤백됩니다.

DB에 넣기 전에 파싱 결과만 확인하려면 `build-sql`로 검수 문서와 적재 SQL만 만듭니다.

```bash
python -m admin build-sql data/2026통계연보.hwpx --year 2026 --out admin/workspaces/rebuild-2026
```

주요통계집도 같은 명령으로 HWPX 원본을 직접 적재합니다. 주요통계집은 같은 해에 상반기와
하반기 두 판이 나오므로 `--publication-kind major_statistics`와 함께 `--period H1|H2`를
반드시 지정합니다. 통계연보는 반기가 없어 `--period`를 쓰지 않습니다.

```bash
python -m admin ingest data/2025년_하반기_주요통계집.hwpx \
  --year 2025 --publication-kind major_statistics --period H2 --mode replace --embedding bge-m3
```

관리자 화면도 두 발간물을 모두 HWPX로 받습니다. **발간물 종류**에서 주요통계집을 고르면
**발간 반기** 칸이 나타나며, 반기를 고르지 않으면 적재를 거부합니다.

### 주요통계집 계층 복원 규칙

주요통계집은 통계연보와 표기가 달라 별도 파서(`admin/backend/services/load_major_statistics.py`)를
씁니다. 본문 항목 번호는 `4-38 서해 5도`처럼 장-항목 두 단계뿐이고, 그 아래 통계는 번호 없이
두 가지 표제로 적힙니다.

```
❍ 서해 5도 인구 : 8,151명(남 4,860 / 여 3,291)   ← 3계층. 제목 자체가 값을 담는다
  - 연평면 1,993 / 백령면 4,722 / 대청면 1,436    ← 그 3계층의 내용
  ※ 옹진군 전체 인구(19,996명)의 40.8%            ← 그 3계층의 주석
< 지구촌 새마을운동 현황 >                        ← 4계층. 바로 아래 표의 실제 제목
```

그래서 한 항목은 통계 하나가 아니라 `❍`/`<>` 묶음마다 하나씩 통계 행이 됩니다.
`4-38 서해 5도`는 `chapter_no=4`, `section_no=38`, `section=서해 5도`를 공유하는 네 개의
통계 행(`4-38-1`~`4-38-4`)이 되고, `level3_title`에 `❍` 제목이, `level4_title`에 `<>` 제목이
들어갑니다. 문서에 번호가 없으므로 `level3_no`와 `level4_no`는 비웁니다. `<>`가 바로 앞
`❍`의 하위인지는 그 `❍`가 자기 본문을 가졌는지로 가릅니다. 제목만 있는 `❍`(예:
`❍ 2024년 모금현황`) 아래의 `<>`는 하위 표이고, 이미 설명 문단을 가진 `❍` 뒤의 `<>`는
나란히 놓인 별개의 표입니다.

표가 없는 `❍` 묶음도 본문에 수치가 그대로 적혀 있으므로 제목 줄과 내용 줄을 한 컬럼짜리
표로 만들어 `stat_tables.table_md`와 `body`에 넣습니다. 그래야 표 검색과 임베딩이 통계연보와
같은 경로로 동작합니다. 1열짜리 표는 수치 표가 아니라 본문을 감싼 글상자이므로 줄로 풀어
본문처럼 다시 분류하고, 판권지는 본문에서 뺍니다.

`title_ko`는 항목 이름과 묶음 제목을 겹치지 않게 이어 만듭니다. `개요`, `기부 추이`처럼
항목 이름 없이는 뜻이 통하지 않는 제목이 많고, `서해 5도 관광객`처럼 이미 항목 이름을 품은
제목도 있기 때문입니다.

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
