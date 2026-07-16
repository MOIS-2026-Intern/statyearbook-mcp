<!-- 이 문서는 관리자 백엔드의 계층 구조와 공식 실행 진입점을 설명한다. -->
# 관리자 백엔드 구조

`admin.backend`는 사용자용 `backend`와 독립된 관리자 애플리케이션입니다.

```text
backend/
├── app.py             FastAPI 조립과 frontend mount
├── cli.py             ingest/serve/promote 통합 CLI
├── config.py          관리자 전용 환경 설정
├── controllers/       HTTP 요청·응답 경계
├── models/            작업 옵션과 산출물 이름
├── repositories/      SQLite/PostgreSQL 접근
└── services/          파싱·DML·임베딩·검증 로직
```

공식 실행 진입점은 통합 CLI와 관리자 웹 두 가지입니다.

```bash
python -m admin ingest data/2026_통계연보.hwpx --year 2026
python -m admin serve
```

개별 단계용 CLI는 통합 CLI와 중복되므로 제공하지 않습니다. 기본 적재 모드는 같은
연도를 거부하며, 명시적인 `--mode replace`만 해당 연도를 교체합니다.
