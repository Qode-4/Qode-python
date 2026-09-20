# Qode-python

Qode의 코드 인덱싱·검색(RAG) 서비스. FastAPI + PostgreSQL(pgvector) + LangChain.

[Qode-Server](../Qode-Server)(Node.js)가 GitHub 레포를 동기화하면 이 서비스가 그 코드를 청킹·임베딩해 pgvector에 넣고, 사용자 질문이 오면 관련 청크를 찾아 돌려준다. LLM 답변 생성은 Qode-Server가 맡는다.

```
[Qode-Server]  ──POST /index──▶  파싱 → 청킹 → 임베딩 → pgvector 저장
               ──POST /search─▶  번역 → 하이브리드 검색 → 필터 → 중복 제거 → 리랭크 → 청크 반환
```

## 요구 사항

| 항목 | 비고 |
| --- | --- |
| Python | 3.11 이상 (현재 venv는 3.14) |
| PostgreSQL + pgvector | `code_embeddings.embedding vector(1536)`. 설치는 `.docs/pgvector-setup.md` |
| OpenAI API 키 | 임베딩(`text-embedding-3-small`) |
| Google Cloud Translation | 검색 질의를 영어로 번역. 서비스 계정 키 필요 |
| Cohere API 키 | 선택. 리랭크(`rerank-v3.5`). 없으면 벡터 점수 정렬로 폴백 |

## 빠른 시작

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # 아래 환경변수 절 참고
createdb qode                   # 테이블·인덱스·확장은 부팅 시 자동 생성

uvicorn app.api.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

마이그레이션 도구가 없다. 부팅 시 `app/db/init.py`가 `migrations/001_create_code_embeddings.sql`을 그대로 실행한다(`CREATE ... IF NOT EXISTS`라 멱등). 스키마를 바꾸려면 이 SQL 파일을 고친다.

## 환경변수

`app/config.py`가 `load_dotenv(override=True)`로 읽으므로 `.env`가 셸 환경변수를 덮어쓴다.

| 변수 | 필수 | 설명 |
| --- | --- | --- |
| `DATABASE_URL` | O | pgvector가 설치된 PostgreSQL |
| `OPENAI_API_KEY` | O | 임베딩 |
| `GOOGLE_TRANSLATE_PROJECT_ID` | O | GCP 프로젝트 ID. 없으면 `app/retrieval/translate.py` import 시점에 KeyError로 서버가 죽는다 |
| `GOOGLE_APPLICATION_CREDENTIALS` | O | 서비스 계정 키 JSON 경로(예: `./key.json`, gitignore 대상) |
| `APP_ENV` | | `local`(기본) 또는 `production`. 아래 저장소 루트 선택에 쓰인다 |
| `LOCAL_REPO_STORAGE_ROOT`, `PROD_REPO_STORAGE_ROOT` | | 동기화된 레포가 있는 루트. `{루트}/{project_id}/current`를 읽는다. **Qode-Server의 `SYNC_REPO_BASE_DIR`과 같은 위치여야 한다** |
| `SCORE_THRESHOLD` | | 코사인 유사도 하한. 기본 0.1(사실상 꺼짐) |
| `RERANKER_ENABLED` | | 기본 `true`. `false`면 Cohere 없이 벡터 점수 정렬 |
| `COHERE_API_KEY` | | 리랭크. `langchain_cohere`가 직접 읽는다. 없으면 예외를 삼키고 폴백하므로 로그를 봐야 켜졌는지 안다 |
| `LANGSMITH_*` | | 검색 단계마다 `@traceable`이 붙어 있다. langsmith SDK가 직접 읽는다 |

## API

Swagger UI는 FastAPI 기본값인 `/docs`에서 볼 수 있다. 계약 문서는 `.docs/api-contracts.md`.

### `POST /index`

Qode-Server가 레포 동기화를 마친 뒤 호출한다. 해당 `projectId`의 기존 벡터를 **전부 지우고** 다시 임베딩한다(레포 크기에 따라 수십 초).

```json
{ "projectId": "…", "syncJobId": "…" }
```

성공 시 200과 `{ status: "completed", chunks_created, elapsed_ms, repoPath, … }`. 실패 시 **500**과 같은 형태의 `detail`을 돌려준다. 200으로 돌려주면 Qode-Server가 동기화를 성공으로 닫아버리기 때문이다.

### `POST /search`

```json
{ "query": "jwt 검증 함수", "project_id": "…", "top_k": 10 }
```

응답은 `chunks[]`(각각 `content`, `metadata`)와 `search_meta`(`total_found`, `after_filter`, `after_dedup`, `final`, `search_time_ms`). `top_k` 기본값 10은 Qode-Server의 `RAG_TOP_K`와 같이 움직여야 한다. 파이프라인 안에서 예외가 나면 빈 `chunks`와 `search_meta.error`로 200을 돌려준다.

### `GET /health`

`{ "status": "ok" }`. Qode-Server의 인덱싱 클라이언트와 배포 스크립트가 이걸 본다.

## 파이프라인

### 인덱싱 (`app/parsing` → `app/embedding`)

1. `loader.collect_documents`: 허용 확장자(`.ts .tsx .js .jsx .py .java .go .rs .rb .yml .yaml .json .sql`)만 수집. `node_modules`, `dist`, `.git` 등은 건너뛰고, `.env*`, `*.lock`, `*.min.js` 등은 제외. `tests/`나 `*.test.*` 같은 테스트 파일은 버리지 않고 `metadata.is_test=true`로 표시만 한다.
2. `splitter.split_documents`: tree-sitter 문법이 있는 언어는 함수·클래스 정의 단위(AST)로, 나머지는 문자 수(기본 1000자, 겹침 200자)로 자른다. 마크다운 헤더 단위 분할기도 있지만 `.md`가 허용 확장자에 없어 현재는 쓰이지 않는다. 각 청크에 `start_line`/`end_line`을 붙인다.
3. `filters.filter_chunks`: 50자 미만 청크 제거.
4. `embedding.store.reindex`: 프로젝트의 기존 행 삭제 → 100개씩 배치 임베딩 → `code_embeddings`에 INSERT.

청크 메타데이터: `source`, `language`, `extension`, `chunk_index`, `total_chunks`, `start_line`, `end_line`, `project_id`, `file_size`, `is_test`.

### 검색 (`app/retrieval/pipeline.py`)

1. **번역**: Google Translate로 질의를 영어로 바꾼다(코드와 어휘를 맞추기 위해).
2. **하이브리드 검색** (`searcher.hybrid_search`): 프로젝트 청크를 전부 읽어 벡터(코사인) 상위 20개와 BM25 상위 20개를 뽑고 RRF로 합친다. 질의에 "테스트", "mock", "pytest" 같은 단어가 없으면 `is_test=true` 청크는 검색에서 뺀다.
3. **필터**: `SCORE_THRESHOLD` 미만 제거.
4. **중복 제거**: 공백을 정규화한 뒤 본문이 같은 청크 제거.
5. **리랭크**: Cohere `rerank-v3.5`로 재정렬 후 `top_k`개 반환. 실패하거나 꺼져 있으면 벡터 점수 순.

## 테스트

```bash
pytest                              # 30개, DB·외부 API 없이 돈다
pytest tests/parsing -v             # 청킹(AST·라인·마크다운)
pytest tests/retrieval -v           # 검색·필터·중복 제거·리랭크·BM25
pytest tests/api -v                 # /index 실패 응답
```

`tests/fixtures/`는 파싱 검증용 가짜 레포다. `tests/fixtures/node_modules/`는 제외 규칙을 검증하는 자산이므로 지우면 안 된다(`.gitignore`가 루트 `node_modules`만 무시하는 이유).

실제 DB에 넣어 보려면 `python test_manual.py`가 `tests/fixtures`를 `test_project`로 인덱싱한다.

## 검색 품질 평가

`app/eval/`에 두 가지 스크립트가 있다. 둘 다 `dataset.py`의 QA 쌍을 `test_project`에 던진다.

- `python -m app.eval.run_eval`: Recall@5, MRR
- `python -m app.eval.run_eval_ragas`: ragas의 context precision/recall (gpt-4o-mini 채점)

## 디렉터리

```
app/
├── api/main.py        # FastAPI 앱, 라우트 3개
├── config.py          # 환경변수, 레포 경로 해석(경로 탈출 검사 포함)
├── db/init.py         # 부팅 시 마이그레이션 SQL 실행
├── parsing/           # loader(수집) → splitter(청킹) → filters(제외 규칙)
├── embedding/         # embedder(OpenAI) → store(pgvector INSERT/reindex)
├── retrieval/         # pipeline → translate, searcher, filter, dedup, reranker
└── eval/              # 검색 품질 측정
migrations/            # 스키마 SQL
tests/                 # pytest
.docs/                 # 설계 문서(일부는 초기 설계 시점 내용이라 코드와 다를 수 있음)
```

## 배포

`main`에 푸시하면 GitHub Actions(`.github/workflows/deploy.yml`)가 EC2에 SSH로 접속해 `/srv/qode-python`에서 `git pull`, `pip install -r requirements.txt`, `systemctl restart qode-python`을 실행하고 `/health`를 확인한다. 작업 브랜치는 `develop`.

## 알아둘 것

- **인증이 없다.** Qode-Server는 `x-qode-internal-token` 헤더를 보내지만 이 서비스는 검사하지 않는다. 포트 8000은 외부에 열지 않는다.
- `.docs/api-contracts.md`의 `/search` 응답 형태(`page_content`, 최상위 `score`)와 `top_k` 기본값 5는 초기 설계다. 실제는 `content`/`metadata`, 기본 10이며 점수는 `metadata.score`(리랭크 시 `vector_score`, `rerank_score` 추가)에 있다.
- 리랭커의 `top_n` 기본값이 3이라 명시적으로 `len(docs)`로 올려 둔 상태다. 손대면 LLM에 청크가 3개만 간다.
