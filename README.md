# statyearbook-mcp
행정안전통계연보를 챗봇으로도 만나보세요


## 채팅 실행 구조

- `frontend/`: React 채팅 UI
- `backend/`: FastAPI REST API, 채팅 모델 provider adapter, MCP host
- `app/`: 통계 검색·표 조회·시각화를 제공하는 MCP server
- `shared/`: 관리자와 MCP server가 함께 사용하는 임베딩·pgvector 공용 코드
- `db/`: 로컬 PostgreSQL·운영 Supabase 공통 최종 `schema.sql`과 DB 설정
- `server.py`: 기존 statyearbook MCP server

백엔드는 프론트의 `POST /api/chat` 요청을 받아 `STATYEARBOOK_MODEL_PROVIDER`로 선택된 모델 host를 호출하고, 모델이 필요하다고 판단한 MCP 도구를 로컬 `server.py`에 stdio로 연결해 실행합니다. 기본 provider는 `openai`입니다.

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m backend
```

프론트는 `frontend/.env.local`에 실제 API 주소를 지정한 뒤 실행합니다.

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_USE_MOCK_API=false
```

```bash
cd frontend
npm run dev
```

## 관리자 통합 적재

새 통계연보의 파싱, 누적 적재 DML 생성·실행, 임베딩 DML 생성·실행과 검증은 관리자
애플리케이션으로 분리되어 있습니다.

```bash
python -m admin ingest data/2026_통계연보.hwpx --year 2026
```

관리자 웹은 사용자용 백엔드와 다른 프로세스와 포트를 사용합니다.

```bash
python -m admin serve
# http://127.0.0.1:8100
```

환경 분리와 운영 DB 활성화 절차는 `admin/README.md`를 참고하세요.
