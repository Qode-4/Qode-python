# RAG 파이프라인 상세

## 전체 흐름

```
인덱싱 (오프라인, Repo Sync 시):
[파일 수집] → [청킹] → [임베딩] → [벡터 DB 저장]
   채연          채연       예지         예지

질의응답 (온라인, 사용자 질문 시):
[질문 임베딩] → [벡터 검색] → [정제/rerank] → [청크 반환]
    혜수           혜수           혜수           혜수
                                                  ↓ HTTP
                                          [프롬프트 조립] → [LLM 호출] → [응답]
                                              수빈            수빈         수빈
                                           (Node.js)       (Node.js)    (Node.js)
```

## Stage 1: 파싱 + 청킹 (채연)

### 파일 수집

```python
# 허용 확장자
ALLOWED_EXTENSIONS = [
    ".ts", ".tsx", ".js", ".jsx", ".py", ".java", ".go", ".rs", ".rb",
    ".md", ".txt", ".yml", ".yaml", ".json", ".sql",
]

# 제외 디렉터리
EXCLUDE_DIRS = [
    "node_modules", ".git", "dist", "build", ".next",
    "coverage", "__pycache__",
]

# 제외 파일 패턴
EXCLUDE_PATTERNS = [
    ".env", ".env.*", "credentials.*",
    "*.lock", "package-lock.json",
    "*.min.js", "*.map",
]
```

### 청킹

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,       # 청크 최대 1000자
    chunk_overlap=200,     # 청크 간 200자 겹침 (맥락 유지)
    separators=["\n\n", "\n", " ", ""],
)
```

언어별 코드 인식 분할도 가능:

```python
from langchain.text_splitter import Language

ts_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.JS,
    chunk_size=1500,
    chunk_overlap=200,
)
```

### 출력 형태

```python
Document(
    page_content="청크 텍스트...",
    metadata={
        "source": "src/auth.ts",
        "language": "typescript",
        "extension": ".ts",
        "chunk_index": 0,
        "total_chunks": 5,
        "start_line": 1,
        "end_line": 30,
        "project_id": "proj_123",
    }
)
```

## Stage 2: 임베딩 + 벡터 저장 (예지)

### 임베딩

```python
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")  # 1536차원
# 또는 text-embedding-3-large (3072차원, 더 정확하지만 비용 2배)
```

### 벡터 저장

```python
from langchain_community.vectorstores import PGVector

vectorstore = PGVector.from_documents(
    documents=chunks,
    embedding=embeddings,
    connection_string="postgresql://...",
    collection_name="code_embeddings",
)
```

### 비용 추정

```
text-embedding-3-small 기준:
- 파일 80개 × 청크 5개 = 400 청크
- 400 × 250 토큰 = 100,000 토큰
- 비용: $0.002 (Repo Sync 1회당 약 0.2센트)
```

## Stage 3: 검색 + 검증 (혜수)

### 검색 파이프라인

```python
async def search(request: SearchRequest) -> SearchResult:
    # 1. 벡터 검색 (top-k)
    raw_results = retriever.invoke(request.query)

    # 2. threshold 필터링 (유사도 0.7 미만 제거)
    filtered = filter_by_threshold(raw_results, threshold=0.7)

    # 3. dedup (중복 청크 제거)
    deduped = deduplicate_chunks(filtered)

    # 4. rerank (메타데이터 가중치)
    reranked = metadata_rerank(deduped)

    return SearchResult(chunks=reranked, ...)
```

### FastAPI 엔드포인트

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/search")
async def search_endpoint(request: SearchRequest) -> SearchResult:
    return await search(request)

@app.post("/index")
async def index_endpoint(request: IndexRequest):
    # 파일 수집 → 청킹 → 임베딩 → 저장
    ...
```

## Stage 4: 질의응답 + LangSmith (수빈, Node.js)

수빈은 기존 Qode 서버(TypeScript)에서 작업한다.

### Python 서비스 호출

```typescript
const response = await fetch("http://rag-service:8000/search", {
    method: "POST",
    body: JSON.stringify({
        query: question,
        project_id: projectId,
        top_k: 5,
    }),
});
const searchResult = await response.json();
```

### 프롬프트 조립

```typescript
// 기존 CAG: getAnalysisCache() → 캐시 전체 주입
// RAG: searchChunks() → 관련 청크만 주입

const contextBlock = searchResult.chunks
    .map(c => `--- ${c.metadata.source} ---\n${c.page_content}`)
    .join("\n\n");

const prompt = `다음 코드를 참고하여 질문에 답하세요.\n\n${contextBlock}\n\n질문: ${question}`;
```

## 단계 간 인터페이스 정리

```
채연 → 예지:  Document(page_content, metadata)  # LangChain 표준
예지 → DB:    code_embeddings 테이블에 INSERT
혜수 → DB:    code_embeddings 테이블에서 SELECT
혜수 → 수빈:  SearchResult(chunks, search_meta)  # HTTP JSON
```
