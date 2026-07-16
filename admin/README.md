<!-- 이 문서는 통계연보 관리자 CLI, 웹 실행과 운영 승격 절차를 설명한다. -->
# 통계연보 관리자

운영 사용자용 채팅 서버와 완전히 분리된 파싱·적재·임베딩 애플리케이션입니다.
기본값은 `127.0.0.1:8100`이며 운영 DB 대상은 명시적으로 활성화하기 전까지 사용할 수 없습니다.

```text
admin/
├── backend/
│   ├── controllers/
│   ├── models/
│   ├── repositories/
│   └── services/
├── frontend/
├── state/
└── workspaces/
```

`state`와 `workspaces`는 실행 중 생성되는 관리자 전용 데이터이며 Git에 포함되지 않습니다.

## 한 명령으로 로컬 적재

```bash
python -m admin ingest data/2026_통계연보.hwpx \
  --year 2026 \
  --title "2026 행정안전통계연보" \
  --target local \
  --mode reject \
  --embedding bge-m3
```

작업 결과는 `admin/workspaces/YYYYMMDD-HHMMSS-ffffff/`에 보존됩니다.

- `yearbook_source.hwpx`: 업로드 원본
- `yearbook_parsed.json`: 구조화 파싱 결과
- `yearbook_review.md`: 사람 검수용 문서
- `yearbook_load.sql`: ID에 독립적인 누적 적재 DML
- `yearbook_title_embeddings.sql`: 모델 profile과 실제 벡터를 포함한 임베딩 DML

로컬 DB 적재는 두 SQL 산출물을 그대로 실행하는 방식입니다. Python 코드는 HWPX 파싱,
적재 SQL 생성과 임베딩 벡터 계산·SQL 생성을 담당하며, 통계 데이터와 임베딩 벡터는 각각
`yearbook_load.sql`, `yearbook_title_embeddings.sql`을 실행할 때만 DB에 반영됩니다.

같은 연도를 의도적으로 교체할 때만 `--mode replace`를 사용합니다. 다른 연도 데이터는
삭제하지 않습니다.

## 관리자 웹 실행

```bash
cp admin/.env.admin.example admin/.env.admin
python -m admin serve
```

브라우저에서 `http://127.0.0.1:8100`을 엽니다. 파일 업로드, 옵션 선택, 단계별 진행률,
오류 상세, 적재 건수 검증과 산출물 다운로드를 한 화면에서 사용할 수 있습니다.

관리자 상태는 Python 표준 라이브러리인 `sqlite3`로
`admin/state/admin_jobs.sqlite3`에 저장되므로 별도 SQLite 설치가 필요하지 않습니다.
작업 파일은 `admin/workspaces/`에 저장됩니다. 둘 다 사용자용 서비스와 분리되며 Git에
포함되지 않습니다.

## 운영 DB 적용 준비

운영 대상은 기본 비활성화되어 있습니다. 로컬 작업이 완료되고 산출물 SQL을 검수한 뒤
관리자 전용 환경에서만 다음 값을 설정합니다.

```dotenv
STATYEARBOOK_ADMIN_API_TOKEN=긴-관리자-전용-토큰
STATYEARBOOK_ADMIN_ENABLE_PRODUCTION_TARGET=true
STATYEARBOOK_ADMIN_PRODUCTION_DSN=postgresql://...
```

운영 배포 시 사용자용 `Dockerfile`이 아니라 `admin/Dockerfile`을 별도 이미지로 빌드하고,
사내망/VPN 또는 접근제어 프록시 뒤에 배치해야 합니다. 사용자용 백엔드에는 관리자 router나
업로드 디렉터리를 포함하지 않습니다.

```bash
docker build -f admin/Dockerfile -t statyearbook-admin .
```

로컬에서 완료된 job의 SQL을 검수한 뒤에는 모델을 다시 실행하지 않고 두 DML만 운영 DB에
적용할 수 있습니다. 운영 대상 환경변수와 확인 연도가 모두 맞아야 실행됩니다.

```bash
python -m admin promote <job-id> --confirm-year 2026
```

이 명령은 완료된 job의 `yearbook_load.sql`을 먼저 적용하고, 존재하면
`yearbook_title_embeddings.sql`을 이어서
적용합니다. 따라서 운영 서버에는 Hugging Face 접속이나 모델 추론 장치가 없어도 됩니다.

향후에는 현재 SQLite 작업 큐를 Redis/Celery 또는 사내 작업 큐 adapter로 교체하면 여러
관리자 인스턴스로 확장할 수 있습니다. 전체 흐름은 `YearbookIngestionService`에
있으므로 CLI와 웹 API는 그대로 유지할 수 있습니다.
