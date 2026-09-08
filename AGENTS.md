# AGENTS.md

이 저장소에서 작업하는 AI 코딩 에이전트를 위한 안내다.

## 프로젝트 개요

Qode의 RAG 파이프라인을 담당하는 Python 서비스. 기존 Qode 서버(Node.js/Fastify)의 CAG 방식을 RAG로 전환하는 것이 목표다. 이 서비스는 **인덱싱과 검색만** 담당하고, LLM 호출·프롬프트 조립·SSE 스트리밍은 Node.js 서버 몫이다.

```
[Node.js Qode 서버] --HTTP--> [이 프로젝트] --> [PostgreSQL + pgvector] / [OpenAI 임베딩]
```

README와 `.docs/`가 한국어로 작성되어 있고 코드 주석도 한국어다. 새 코드도 같은 언어를 따른다.

## 명령어

```bash
source venv/bin/activate
pip install -r requirements.txt

# 서버 실행 (lifespan에서 migrations/001을 실행해 테이블·인덱스 자동 생성)
uvicorn app.api.main:app --reload --port 8000

# 테스트: 파일명이 test_*.py가 아니라 모듈명과 같아서 pytest 자동 수집이 안 된다. 경로를 명시해야 한다.
pytest tests/retrieval/filter.py -v
pytest tests/retrieval/dedup.py -v

# retrieval 평가 (DB에 test_project가 인덱싱되어 있어야 함)
python -m app.eval.run_eval          # Recall@k, MRR
python -m app.eval.run_eval_ragas    # ragas Context Precision/Recall (LLM 판정, OpenAI 과금)

# 로컬 픽스처로 인덱싱 스모크 테스트
python test_manual.py
```

`conftest.py`가 repo 루트를 `sys.path`에 넣으므로 pytest는 항상 루트에서 실행한다.

## 아키텍처

두 개의 파이프라인이 있고, 각각 하나의 진입 함수 뒤에 숨겨져 있다.

**인덱싱** — `POST /index` → `resolve_repo_path()` → `parse_and_chunk()` → `reindex()`
- `app/config.py:resolve_repo_path()` — `APP_ENV`에 따라 LOCAL/PROD 저장소 루트를 고르고 `{root}/{project_id}/current`를 반환. path traversal 방어(`is_relative_to`)가 여기 있으므로 repo 경로는 반드시 이 함수를 거쳐야 한다.
- `app/parsing/__init__.py:parse_and_chunk()` — 수집(`loader`) → 언어별 청킹(`splitter`) → 짧은 청크 제거(`filters`). 확장자 허용목록·제외 디렉터리·확장자→언어 매핑은 전부 `app/parsing/filters.py` 상수에 모여 있다.
- `splitter.py`는 청크를 원본 텍스트에서 되찾아 `start_line`/`end_line`을 메타데이터에 넣는다. 앞 50자 문자열 검색 기반이라 중복 라인이 많은 파일에서는 부정확할 수 있다.
- `app/embedding/store.py:reindex()` — project_id 단위로 **전체 삭제 후 재삽입**. 증분 업데이트는 없다.

**검색** — `POST /search` → `search_pipeline()` → search → filter → dedup → rerank
- `app/retrieval/pipeline.py`가 4단계를 순서대로 호출하고 각 단계의 잔존 개수를 `search_meta`에 담는다. 단계를 추가하려면 여기와 `search_meta` 양쪽을 고친다.
- `searcher.py:CodeRetriever`는 LangChain `BaseRetriever` 구현체지만 벡터 검색은 psycopg raw SQL(`embedding <=> %s::vector`)로 직접 한다. langchain-postgres의 PGVector 스토어는 쓰지 않는다.
- 유사도는 `1 - cosine_distance`이고 `SCORE_THRESHOLD` 미만은 `filter.py`에서 잘린다. **코드 기본값 0.7과 실제 쓰는 값이 다르다** — `.env.example`은 0.1이고, 0.7은 한국어 질문↔코드 코사인 대역(0.3~0.6)을 대부분 걸러낸다. 0.1은 필터를 사실상 끈 상태라 `search_meta`의 filter 단계가 무손실로 찍힌다. 검색 결과가 비면 이 값부터 의심한다.
- `reranker.py`는 아직 score 정렬만 한다(Cross-encoder는 TODO).

**에러 처리 규약**: `/index`와 `search_pipeline`은 예외를 잡아서 `status: "failed"` 또는 빈 `chunks` + `search_meta.error`를 200으로 반환한다. Node.js 서버가 HTTP 에러가 아닌 응답 본문으로 실패를 판별하므로 이 형태를 깨지 말 것.

## DB

단일 테이블 `code_embeddings` (`migrations/001_create_code_embeddings.sql`). `vector(1536)` — text-embedding-3-small 차원에 묶여 있으므로 임베딩 모델을 바꾸면 마이그레이션과 재인덱싱이 함께 필요하다. HNSW(cosine) + project_id + metadata(gin) 인덱스.

`init_database()`는 서버 기동 시 마이그레이션을 그대로 실행한다(모두 `IF NOT EXISTS`). DB 유저에게 extension 생성 권한이 필요하고, pgvector가 없으면 명시적 에러를 낸다. 로컬 설치는 `.docs/pgvector-setup.md` 참고.

## 환경 변수 (.env)

`.env.example`이 전체 목록이자 각 값의 설명이다. 새 환경변수는 양쪽에 함께 추가한다.

코드가 읽는 키는 이 6개뿐이다: `DATABASE_URL`, `OPENAI_API_KEY`, `SCORE_THRESHOLD`, `APP_ENV`(`local`|`production`), `LOCAL_REPO_STORAGE_ROOT`, `PROD_REPO_STORAGE_ROOT`.

`LOCAL_REPO_STORAGE_ROOT`는 절대 경로로 쓰면 레포를 옮겨도 따라오지 않는다. 경로가 없으면 만들어 버리므로 에러 없이 옛 위치에 쌓인다 — 인덱싱이 빈 결과를 내면 이 경로부터 본다.

모든 모듈이 `load_dotenv(override=True)`를 호출한다 — `.env`가 기존 셸 환경변수를 덮어쓴다.

## 알아둘 것

- 모듈 소유자가 나뉘어 있다: `parsing/`(채연), `embedding/`(예지), `retrieval/`(혜수). 남의 모듈을 광범위하게 리팩터링하기 전에 확인이 필요하다.
- `tests/retrieval/searcher.py`는 현재 `search()`의 시그니처(`query, project_id, top_k`)와 맞지 않는 옛 async 호출을 하고 있어 그대로는 실패한다.
- `.data/`는 인덱싱 대상 레포가 동기화되는 로컬 저장소이고 gitignore 대상이다.
- API 계약의 단일 출처는 `.docs/api-contracts.md`와 `.docs/qode-server-integration.md`다. 요청/응답 스키마를 바꾸면 Node.js 서버와 함께 맞춰야 한다.
