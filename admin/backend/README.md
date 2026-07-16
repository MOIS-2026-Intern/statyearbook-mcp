# 관리자 백엔드 구조

`admin.backend`는 사용자용 `backend`와 독립된 관리자 애플리케이션입니다.

```text
backend/
├── app.py                         FastAPI 조립과 정적 frontend mount
├── cli.py                         ingest/serve/promote 통합 CLI
├── config.py                      관리자 전용 환경 설정
├── controllers/                   HTTP 요청·응답 경계
├── models/                        작업 옵션과 산출물 이름
├── repositories/                  SQLite/PostgreSQL 접근
├── services/                      파싱·DML·임베딩·검증 orchestration
└── commands/                      장애 분석용 저수준 명령
```

일반 관리자는 저수준 명령 대신 다음 통합 명령 또는 관리자 웹을 사용합니다.

```bash
python -m admin ingest data/2026_통계연보.hwpx --year 2026
python -m admin serve
```

## 저수준 명령

특정 단계만 진단할 때 모듈로 실행합니다.

```bash
python -m admin.backend.services.yearbook_parser_service data/통계연보.hwpx \
  --year 2026 \
  --json-out admin/workspaces/manual/yearbook_parsed.json \
  --md-out admin/workspaces/manual/yearbook_review.md

python -m admin.backend.commands.load_yearbook_command \
  admin/workspaces/manual/yearbook_parsed.json \
  --emit-sql admin/workspaces/manual/yearbook_load.sql

python -m admin.backend.commands.embed_statistics_command \
  --year 2026 \
  --emit-sql admin/workspaces/manual/yearbook_title_embeddings.sql
```

기본 적재 모드는 같은 연도를 거부하며, 명시적인 `--mode replace`만 해당 연도를
교체합니다. 다른 연도 데이터는 삭제하지 않습니다.
