# API 및 인터페이스 계약

## 외부 API (Node.js 서버 → Python 서비스)

### POST /search

사용자 질문에 대한 관련 청크를 검색한다.

```python
# Request
class SearchRequest(BaseModel):
    query: str              # 사용자 질문
    project_id: str         # 프로젝트 ID
    top_k: int = 5          # 반환할 청크 수

# Response
class RetrievedChunk(BaseModel):
    page_content: str       # 청크 텍스트
    score: float            # 유사도 점수 (0~1)
    metadata: dict          # source, language, chunk_index, start_line, end_line, project_id

class SearchResult(BaseModel):
    chunks: list[RetrievedChunk]
    search_meta: dict       # total_found, search_time_ms
```

### POST /index

프로젝트의 코드를 인덱싱한다. Repo Sync 완료 후 호출.

```python
# Request
class IndexRequest(BaseModel):
    project_id: str         # 프로젝트 ID
    repo_path: str          # 동기화된 레포지토리 경로

# Response
class IndexResult(BaseModel):
    status: str             # "completed" | "failed"
    chunks_created: int     # 생성된 청크 수
    elapsed_ms: int         # 소요 시간
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

## 내부 인터페이스 (팀원 간)

### 채연 → 예지: Document (LangChain 표준)

채연의 파싱+청킹 결과를 예지의 임베딩 단계로 전달.

```python
from langchain.schema import Document

# 채연이 반환하는 것
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

### 예지 → 혜수: pgvector 테이블

예지가 저장한 벡터를 혜수가 검색한다. 직접 함수 호출이 아니라 DB를 통해 연결.

```sql
-- 예지가 저장
INSERT INTO code_embeddings (embedding, content, metadata, project_id)
VALUES ($1, $2, $3, $4);

-- 혜수가 검색
SELECT content, metadata, 1 - (embedding <=> $1) AS score
FROM code_embeddings
WHERE project_id = $2
ORDER BY embedding <=> $1
LIMIT $3;
```

### 혜수 → 수빈: SearchResult (HTTP JSON)

혜수의 Python 서비스가 수빈의 Node.js 서버에 HTTP로 반환.

```json
{
    "chunks": [
        {
            "page_content": "function verifyToken...",
            "score": 0.92,
            "metadata": {
                "source": "src/auth.ts",
                "language": "typescript",
                "chunk_index": 0,
                "start_line": 12,
                "end_line": 30,
                "project_id": "proj_123"
            }
        }
    ],
    "search_meta": {
        "total_found": 15,
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
