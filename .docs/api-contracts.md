# API 및 인터페이스 계약

## 외부 API (Node.js 서버 → Python 서비스)

### POST /search

사용자 질문에 대한 관련 청크를 검색한다.

```python
# Request
class SearchRequest(BaseModel):
    query: str              # 사용자 질문
    project_id: str         # 프로젝트 ID
    top_k: int = 10         # 반환할 청크 수. Qode-Server rag.service.ts 의 RAG_TOP_K 와 같이 움직인다

# Response
class RetrievedChunk(BaseModel):
    content: str            # 청크 텍스트
    metadata: dict          # source, language, chunk_index, start_line, end_line, project_id, is_test,
                            # score(코사인). 리랭크가 동작하면 vector_score, rerank_score 추가

class SearchResult(BaseModel):
    chunks: list[RetrievedChunk]
    search_meta: dict       # total_found, after_filter, after_dedup, final, search_time_ms
                            # 파이프라인 예외 시 chunks=[] 와 search_meta.error 로 200 응답
```

Qode-Server 쪽은 `normalizeSearchResult()`가 `content` → `page_content`로, `metadata.score`를 밖으로 꺼내 내부 타입으로 바꾼다.

### POST /index

프로젝트의 코드를 인덱싱한다. Repo Sync 완료 후 호출.

```python
# Request
class IndexRequest(BaseModel):
    projectId: str          # 프로젝트 ID
    syncJobId: str          # Node.js 서버의 Repo Sync 작업 ID

# Response
class IndexResult(BaseModel):
    status: str             # "completed" | "failed"
    projectId: str          # 프로젝트 ID
    syncJobId: str          # Repo Sync 작업 ID
    appEnv: str             # 실행 환경 ("local" | "production" 등)
    repoPath: str | None    # 실제 인덱싱한 로컬 repo 경로 (성공 시)
    chunks_created: int     # 생성된 청크 수
    elapsed_ms: int         # 소요 시간
    error: str | None       # 실패 사유 (실패 시)
```

### GET /health

서비스 상태 확인.

```python
# Response
{
    "status": "ok"
}
```

---

## 내부 인터페이스 (모듈 간)

### parsing → embedding: Document (LangChain 표준)

파싱+청킹 결과를 임베딩 단계로 전달.

```python
from langchain.schema import Document

# parse_and_chunk() 가 반환하는 것
documents: list[Document]

# 각 Document의 구조
Document(
    page_content="function verifyToken(token: string) {\n  return jwt.verify(...)\n}",
    metadata={
        "source": "src/auth.ts",        # 파일 경로
        "language": "typescript",        # 언어
        "extension": ".ts",             # 확장자
        "chunk_index": 0,               # 이 파일의 몇 번째 청크
        "total_chunks": 5,              # 이 파일의 전체 청크 수
        "start_line": 12,               # 원본 파일 시작 라인
        "end_line": 30,                 # 원본 파일 끝 라인
        "project_id": "proj_123",       # 프로젝트 ID
    }
)
```

### embedding → retrieval: pgvector 테이블

저장된 벡터를 검색 단계가 읽는다. 직접 함수 호출이 아니라 DB를 통해 연결.

```sql
-- embedding.store 가 저장
INSERT INTO code_embeddings (embedding, content, metadata, project_id)
VALUES ($1, $2, $3, $4);

-- retrieval.searcher 가 검색
SELECT content, metadata, 1 - (embedding <=> $1) AS score
FROM code_embeddings
WHERE project_id = $2
ORDER BY embedding <=> $1
LIMIT $3;
```

### retrieval → Qode-Server: SearchResult (HTTP JSON)

Python 서비스가 Node.js 서버에 HTTP로 반환.

```json
{
    "chunks": [
        {
            "content": "function verifyToken...",
            "metadata": {
                "source": "src/auth.ts",
                "language": "typescript",
                "chunk_index": 0,
                "start_line": 12,
                "end_line": 30,
                "project_id": "proj_123",
                "is_test": false,
                "score": 0.92
            }
        }
    ],
    "search_meta": {
        "total_found": 15,
        "after_filter": 15,
        "after_dedup": 12,
        "final": 10,
        "search_time_ms": 45
    }
}
```

---

## metadata 필드 명세

모든 단계에서 공통으로 사용하는 메타데이터.

| 필드 | 타입 | 필수 | 설명 | 예시 |
|------|------|------|------|------|
| `source` | string | O | 원본 파일 경로 (레포 루트 기준 상대 경로) | `"src/auth.ts"` |
| `language` | string | O | 프로그래밍 언어 | `"typescript"` |
| `extension` | string | O | 파일 확장자 | `".ts"` |
| `chunk_index` | int | O | 이 파일에서의 청크 순번 (0부터) | `0` |
| `total_chunks` | int | O | 이 파일의 전체 청크 수 | `5` |
| `start_line` | int | X | 원본 파일 시작 라인 | `12` |
| `end_line` | int | X | 원본 파일 끝 라인 | `30` |
| `project_id` | string | O | 프로젝트 ID | `"proj_123"` |
| `file_size` | int | X | 원본 파일 크기 (바이트) | `2048` |
| `is_test` | bool | O | 테스트 디렉터리/파일 여부. 테스트를 묻는 질의가 아니면 검색에서 제외 | `false` |
