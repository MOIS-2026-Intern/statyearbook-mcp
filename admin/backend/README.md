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
└── services/
    ├── load_*.py      파싱·DML·적재·임베딩·검증·운영 승격
    ├── job_queue.py   웹 요청의 적재 작업 순차 실행
    └── upload.py      웹 업로드 스트림 저장
```

하위 폴더가 역할을 나타내므로 파일명에는 `service`, `controller`, `repository`, `model`
접미사를 반복하지 않습니다. `services`에서는 통계연보 적재 파이프라인에 참여하는 파일만
`load_`로 시작합니다.

공식 실행 진입점은 통합 CLI와 관리자 웹 두 가지입니다.

```bash
python -m admin ingest data/2026_통계연보.hwpx --year 2026
python -m admin serve
```

개별 단계용 CLI는 통합 CLI와 중복되므로 제공하지 않습니다. 기본 적재 모드는 같은
연도를 거부하며, 명시적인 `--mode replace`만 해당 연도를 교체합니다.
