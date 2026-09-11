# 혜수 — 검색 + 검증 (Retriever + Validation)

> RAG 파이프라인의 세 번째 단계.
> 사용자 질문에 맞는 청크를 찾고, 검색 품질을 검증하는 역할.
> **Python** (LangChain Python) — 2단계 LlamaIndex 도입 대비
> Node.js Qode 서버에 검색 API를 제공한다.

---

## 목표

사용자 질문이 들어오면 벡터 DB에서 관련 청크를 검색하고, 정제/rerank를 거쳐 결과를 반환한다. Node.js 서버(수빈)가 HTTP로 호출할 수 있는 검색 API를 제공한다.

---

## 검색 API 엔드포인트

Node.js Qode 서버가 호출하는 API:

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/search")
async def search_endpoint(request: SearchRequest) -> SearchResult:
    """Node.js Qode 서버에서 호출하는 검색 API"""
    return await search(request)
```

### Request

```python
from pydantic import BaseModel

class SearchRequest(BaseModel):
    query: str           # "인증 로직이 어디에 있어?"
    project_id: str      # 프로젝트 ID
    top_k: int = 5       # 상위 몇 개 (기본 5)
```

### Response (수빈에게 넘기는 것)

```python
class RetrievedChunk(BaseModel):
    page_content: str
    score: float
    metadata: dict       # source, language, chunk_index, start_line, end_line, project_id

class SearchResult(BaseModel):
    chunks: list[RetrievedChunk]
    search_meta: dict    # total_found, search_time_ms
```

---

## 작업 목록

### 1. 기본 Retriever 구현

LangChain Python의 PGVector에서 Retriever를 생성한다.

```python
from langchain_community.vectorstores import PGVector

# 예지가 셋업한 vectorstore를 가져와서 Retriever로 변환
retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={
        "k": 5,
        "filter": {"project_id": project_id},
    },
)

# 검색 실행
results = retriever.invoke("인증 로직이 어디에 있어?")
# → [Document, Document, ...] (유사도 높은 순)
```

또는 직접 SQL로 검색:

```sql
-- 코사인 유사도 기반 검색
SELECT
  content,
  metadata,
  1 - (embedding <=> $1) AS score
FROM code_embeddings
WHERE project_id = $2
ORDER BY embedding <=> $1
LIMIT $3;
```

### 2. top-k 실험 (3, 5, 10 비교)

```python
async def experiment_top_k(query: str, project_id: str):
    for k in [3, 5, 10]:
        retriever = vectorstore.as_retriever(search_kwargs={"k": k})
        docs = retriever.invoke(query)

        print(f"--- top-{k} ---")
        for i, doc in enumerate(docs):
            print(f"{i+1}. [{doc.metadata['source']}] score: {doc.metadata.get('score', 'N/A')}")
            print(f"   {doc.page_content[:100]}...")
```

```
top-k가 너무 적으면 (3):
  - 관련 청크를 놓칠 수 있음
  - 프롬프트가 가벼워서 LLM 응답 빠름

top-k가 너무 많으면 (10):
  - 관련 없는 청크가 섞임 → LLM이 혼란
  - 토큰 비용 증가

보통 5가 기본값.
```

### 3. similarity threshold 설정

```python
def filter_by_threshold(
    chunks: list[RetrievedChunk],
    threshold: float = 0.7,
) -> list[RetrievedChunk]:
    return [c for c in chunks if c.score >= threshold]

# threshold가 너무 높으면 (0.9): 결과 너무 적음
# threshold가 너무 낮으면 (0.5): 관련 없는 청크 포함
# 적정 범위: 0.65 ~ 0.80 (실험으로 결정)
```

**결정할 것:**
- 기본 threshold 값
- threshold 이하일 때 "관련 문서를 찾지 못했습니다" 응답을 줄지

### 4. dedup 로직

같은 파일의 겹치는 청크가 반환되는 경우를 처리한다.

```python
def deduplicate_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen = {}
    for chunk in chunks:
        key = f"{chunk.metadata['source']}_{chunk.metadata['chunk_index']}"
        if key not in seen:
            seen[key] = chunk
    return list(seen.values())

# 또는 텍스트 유사도 기반 dedup
def deduplicate_by_content(
    chunks: list[RetrievedChunk],
    overlap_ratio: float = 0.8,
) -> list[RetrievedChunk]:
    result = []
    for chunk in chunks:
        is_duplicate = any(
            text_overlap_ratio(existing.page_content, chunk.page_content) > overlap_ratio
            for existing in result
        )
        if not is_duplicate:
            result.append(chunk)
    return result
```

**발생하는 이유:**
- 청킹 시 overlap 때문에 인접 청크끼리 내용이 겹침
- 같은 함수가 여러 청크에 걸쳐 있으면 비슷한 벡터가 됨

### 5. rerank 붙이기

```python
# 방법 1: Cohere Rerank API
from langchain.retrievers import ContextualCompressionRetriever
from langchain_cohere import CohereRerank

reranker = CohereRerank(model="rerank-v3.5", top_n=5)
compression_retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=retriever,
)
reranked = compression_retriever.invoke(query)

# 방법 2: 단순 메타데이터 가중치
def metadata_rerank(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    def adjusted_score(chunk):
        score = chunk.score
        # 코드 파일 우선 (문서보다)
        if chunk.metadata["language"] != "markdown":
            score += 0.05
        return score

    return sorted(chunks, key=adjusted_score, reverse=True)
```

**결정할 것:**
- 1단계에서는 메타데이터 가중치로 시작하고, 필요 시 Cohere Rerank로 발전
- 2단계에서 LlamaIndex Query Engine으로 교체 가능

### 6. 전체 검색 파이프라인 조립

```python
import time

async def search(request: SearchRequest) -> SearchResult:
    start_time = time.time()

    # 1. 벡터 검색 (top-k)
    raw_results = retriever.invoke(request.query)

    # 2. threshold 필터링
    filtered = filter_by_threshold(raw_results, threshold=0.7)

    # 3. dedup
    deduped = deduplicate_chunks(filtered)

    # 4. rerank
    reranked = metadata_rerank(deduped)

    return SearchResult(
        chunks=reranked,
        search_meta={
            "total_found": len(raw_results),
            "search_time_ms": int((time.time() - start_time) * 1000),
        },
    )
```

### 7. 검색 결과 검증

```python
from dataclasses import dataclass

@dataclass
class TestCase:
    query: str
    expected_sources: list[str]
    unexpected_sources: list[str] = None

test_cases = [
    TestCase(
        query="인증 로직이 어디에 있어?",
        expected_sources=["src/auth.ts", "src/middleware/auth.ts"],
        unexpected_sources=["src/utils/logger.ts"],
    ),
    TestCase(
        query="데이터베이스 연결 설정",
        expected_sources=["src/config/database.ts"],
    ),
    TestCase(
        query="라우팅 구조",
        expected_sources=["src/routes/index.ts"],
    ),
]

async def run_search_validation(test_cases: list[TestCase]):
    passed = 0
    failed = 0

    for tc in test_cases:
        result = await search(SearchRequest(query=tc.query, project_id="test"))
        sources = [c.metadata["source"] for c in result.chunks]

        all_expected = all(s in sources for s in tc.expected_sources)
        no_unexpected = (
            tc.unexpected_sources is None or
            all(s not in sources for s in tc.unexpected_sources)
        )

        if all_expected and no_unexpected:
            print(f"PASS: \"{tc.query}\"")
            passed += 1
        else:
            print(f"FAIL: \"{tc.query}\"")
            print(f"  기대: {tc.expected_sources}")
            print(f"  실제: {sources}")
            failed += 1

    print(f"\n결과: {passed} passed, {failed} failed")
```

---

## 병렬 작업

채연, 예지와 **병렬 가능**하다.

mock 벡터 데이터를 직접 DB에 넣고 검색 로직 + FastAPI 엔드포인트를 먼저 만들 수 있다.

예지가 pgvector 셋업 + 스키마를 먼저 만들어주면 바로 검색 코드를 작성할 수 있다.

---

## 채연(청킹)과의 피드백 루프

```
혜수: "인증 로직 어디에 있어?" 검색 → auth.ts가 top-5에 안 나옴
  ↓
혜수 → 채연: "auth.ts 청크가 너무 잘게 쪼개져서 맥락이 부족해요"
  ↓
채연: chunk_size 1000 → 1500으로 조정
  ↓
예지: 재임베딩 + 재저장
  ↓
혜수: 다시 검증
```

---

## 타임라인

| 주차 | 작업 | 비고 |
|------|------|------|
| Week 1 | FastAPI 엔드포인트 + 기본 Retriever 구현 | 예지와 스키마/필터링 합의 |
| Week 1-2 | mock 데이터로 top-k 실험 (3, 5, 10) | |
| Week 2 | threshold 필터링 + dedup 로직 | |
| Week 2-3 | 실제 벡터 DB 연결 (예지의 저장 완료 후) | |
| Week 3 | rerank 구현 (메타데이터 가중치부터) | |
| Week 3-4 | 검색 검증 테스트 케이스 작성 + 실행 | 채연과 피드백 루프 |
| Week 4~ | 수빈의 Node.js 서버와 HTTP 연결 | |
