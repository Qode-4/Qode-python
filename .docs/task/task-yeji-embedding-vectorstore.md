# 예지 — 임베딩 + 벡터 저장 + DB 스키마

> RAG 파이프라인의 두 번째 단계.
> 청크를 벡터로 변환하고 DB에 저장하는 역할. 인프라 셋업도 포함.
> **Python** (LangChain Python) — 채연과 같은 Python RAG 서비스 내에서 동작

---

## 목표

채연이 만든 Chunk 리스트를 받아서, OpenAI 임베딩 API로 벡터로 변환하고, Aurora PostgreSQL + pgvector에 저장한다.

---

## 입력 인터페이스 (채연에게 받는 것)

```python
# LangChain Document 형태
# Document(
#   page_content="청크 텍스트...",
#   metadata={
#     "source": "src/auth.ts",
#     "language": "typescript",
#     "chunk_index": 0,
#     "total_chunks": 5,
#     "start_line": 1,
#     "end_line": 30,
#     "project_id": "proj_123",
#   }
# )
```

## 출력 (혜수가 검색하는 대상)

pgvector 테이블에 저장된 벡터 + 메타데이터. 혜수는 LangChain Retriever 또는 SQL로 검색한다.

---

## 작업 목록

### 1. pgvector 셋업

Aurora PostgreSQL에 벡터 확장을 설치한다.

```sql
-- pgvector 확장 설치 (Aurora PostgreSQL에서 지원)
CREATE EXTENSION IF NOT EXISTS vector;

-- 설치 확인
SELECT * FROM pg_extension WHERE extname = 'vector';
```

**확인할 것:**
- Aurora PostgreSQL 버전이 pgvector를 지원하는지 (15.x 이상)
- RDS 파라미터 그룹에서 `shared_preload_libraries`에 pgvector 추가 필요 여부

### 2. 벡터 테이블 스키마 설계

```sql
CREATE TABLE code_embeddings (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding   vector(1536),         -- OpenAI text-embedding-3-small 기준
  content     TEXT NOT NULL,         -- 원본 청크 텍스트
  metadata    JSONB NOT NULL,        -- 메타데이터 (source, language 등)
  project_id  VARCHAR(100) NOT NULL, -- 프로젝트 ID
  created_at  TIMESTAMP DEFAULT NOW(),
  updated_at  TIMESTAMP DEFAULT NOW()
);

-- HNSW 인덱스 (검색 빠름, 추천)
CREATE INDEX idx_embedding_hnsw
  ON code_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- 프로젝트별 필터링용 인덱스
CREATE INDEX idx_project_id ON code_embeddings (project_id);

-- metadata JSONB 검색용 인덱스
CREATE INDEX idx_metadata ON code_embeddings USING gin (metadata);
```

**결정할 것:**
- 인덱스 타입: IVFFlat vs HNSW
- 메타데이터를 JSONB로 저장할지, 개별 컬럼으로 풀어낼지
- 프로젝트별 파티셔닝이 필요한지

### 3. 임베딩 API 호출 로직 구현

```python
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",  # 1536차원, 가장 비용 효율적
    # model="text-embedding-3-large",  # 3072차원, 정확도 높음
)

# 단일 텍스트 임베딩
vector = embeddings.embed_query("인증 로직이 어디에 있어?")
# → [0.012, -0.045, 0.078, ...] (1536개)

# 여러 텍스트 배치 임베딩
vectors = embeddings.embed_documents(
    [chunk.page_content for chunk in chunks]
)
```

**결정할 것:**
- 모델 선택: `text-embedding-3-small` (저렴, 1536차원) vs `text-embedding-3-large` (정확, 3072차원)
- 배치 크기: 한 번에 몇 개씩 임베딩 API를 호출할지
- Rate limit 대응: 대량 파일 인덱싱 시 API 호출 속도 제한 처리

### 4. 배치 임베딩 + 에러 처리

```python
import time

async def batch_embed(
    chunks: list[Document],
    embeddings: OpenAIEmbeddings,
    batch_size: int = 100,
) -> list[list[float]]:
    all_vectors = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.page_content for c in batch]

        try:
            vectors = embeddings.embed_documents(texts)
            all_vectors.extend(vectors)
        except Exception as e:
            if "rate_limit" in str(e).lower():
                time.sleep(60)
                # 같은 배치 재시도
                vectors = embeddings.embed_documents(texts)
                all_vectors.extend(vectors)
            else:
                raise

        print(f"임베딩 진행: {min(i + batch_size, len(chunks))}/{len(chunks)}")

    return all_vectors
```

### 5. PGVectorStore 저장 로직

```python
from langchain_community.vectorstores import PGVector

# 방법 1: LangChain PGVector 사용
vectorstore = PGVector.from_documents(
    documents=chunks,
    embedding=embeddings,
    connection_string="postgresql://user:pass@host:5432/db",
    collection_name="code_embeddings",
)

# 방법 2: 직접 SQL로 저장 (세밀한 제어가 필요하면)
import psycopg2
import json

def save_chunk_with_vector(chunk: Document, vector: list[float], conn):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO code_embeddings (embedding, content, metadata, project_id)
               VALUES (%s, %s, %s, %s)""",
            (
                str(vector),
                chunk.page_content,
                json.dumps(chunk.metadata),
                chunk.metadata["project_id"],
            )
        )
    conn.commit()
```

**결정할 것:**
- LangChain PGVector를 쓸지, 직접 SQL로 할지
- 기존 DB 커넥션 풀을 공유할지, 별도로 만들지

### 6. 재인덱싱 로직

Repo Sync가 다시 실행되면 기존 벡터를 삭제하고 새로 저장해야 한다.

```python
async def reindex(project_id: str, new_chunks: list[Document]):
    # 1. 기존 벡터 삭제
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM code_embeddings WHERE project_id = %s",
            (project_id,)
        )
    conn.commit()

    # 2. 새 벡터 저장
    vectors = await batch_embed(new_chunks, embeddings)
    for chunk, vector in zip(new_chunks, vectors):
        save_chunk_with_vector(chunk, vector, conn)

    print(f"재인덱싱 완료: {len(new_chunks)}개 청크 저장")
```

**결정할 것:**
- 전체 삭제 후 재삽입 vs 변경된 파일만 업데이트 (diff 기반)
- 인덱싱 중 검색이 가능해야 하는지 (다운타임 허용 여부)

### 7. 임베딩 비용 추정

```
text-embedding-3-small 기준:
- 가격: $0.02 / 1M 토큰
- 청크 1개 평균 1000자 ≈ 250 토큰
- 파일 80개 × 청크 평균 5개 = 400 청크
- 400 × 250 = 100,000 토큰
- 비용: $0.002 (Repo Sync 1회당 약 0.2센트)
```

---

## 병렬 작업

채연과 **병렬 가능**하다.

- 예지: pgvector 셋업 + 스키마 설계 + mock Chunk로 임베딩/저장 테스트
- 채연: 파싱 + 청킹 구현

Week 1에서 Chunk 인터페이스만 합의하면 서로 기다릴 필요 없다.

---

## 혜수(검색)와의 연결 포인트

혜수가 검색할 때 이 테이블을 조회한다:

```python
retriever = vectorstore.as_retriever(
    search_kwargs={
        "k": 5,
        "filter": {"project_id": "proj_123"},
    }
)
```

스키마 설계 시 혜수와 **프로젝트별 필터링 방식**을 합의해야 한다.

---

## 타임라인

| 주차 | 작업 | 비고 |
|------|------|------|
| Week 1 | pgvector 셋업 + 스키마 설계 | 채연과 Chunk 인터페이스 합의, 혜수와 필터링 방식 합의 |
| Week 1-2 | 임베딩 API 연결 + 배치 처리 | mock Chunk로 테스트 |
| Week 2 | PGVectorStore 저장 로직 | |
| Week 2-3 | 채연의 파싱+청킹과 연결 | 실제 데이터로 통합 테스트 |
| Week 3 | 재인덱싱 로직 + 비용 모니터링 | |
| Week 3~ | 혜수의 검색과 연결 | 실제 벡터 DB 대상 검색 테스트 |
