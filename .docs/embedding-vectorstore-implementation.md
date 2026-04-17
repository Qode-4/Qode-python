# 임베딩 + 벡터 저장 구현 상세 (예지)

## 개요

채연이 만든 `list[Document]`를 받아서 OpenAI 임베딩 API로 벡터로 변환하고, Aurora PostgreSQL + pgvector에 저장한다.

---

## 모듈 구조

```
app/embedding/
├── __init__.py       # 외부 공개 함수 export
├── embedder.py       # 임베딩 변환 + 배치 처리
└── store.py          # DB 저장 + 재인덱싱
```

---

## 환경 변수

```env
DATABASE_URL=postgresql://유저명:비밀번호@호스트:5432/DB명
OPENAI_API_KEY=sk-... (규오드 계정 API 생서해 사용 혹시 필요하면 말씀해주세요.)
```

---

## DB 셋업

### pgvector 확장 설치 (최초 1회)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 테이블 생성

```sql
CREATE TABLE code_embeddings (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding   vector(1536),          -- OpenAI text-embedding-3-small 기준
  content     TEXT NOT NULL,          -- 원본 청크 텍스트
  metadata    JSONB NOT NULL,         -- 메타데이터 (source, language 등)
  project_id  VARCHAR(100) NOT NULL,  -- 프로젝트 ID
  created_at  TIMESTAMP DEFAULT NOW(),
  updated_at  TIMESTAMP DEFAULT NOW()
);
```

### 인덱스 생성

```sql
-- 벡터 유사도 검색용 (HNSW)
CREATE INDEX idx_embedding_hnsw
  ON code_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- 프로젝트별 필터링용
CREATE INDEX idx_project_id ON code_embeddings (project_id);

-- metadata JSONB 검색용
CREATE INDEX idx_metadata ON code_embeddings USING gin (metadata);
```

---

## 임베딩 모듈 (embedder.py)

```python
from app.embedding.embedder import embed_documents

vectors = embed_documents(chunks)
# 입력: list[Document]
# 출력: list[list[float]] (1536차원 벡터 리스트)
```

### 특징

- 모델: `text-embedding-3-small` (1536차원)
- 배치 처리: 100개씩 나눠서 API 호출
- Rate limit 대응: 초과 시 60초 대기 후 재시도

---

## 저장 모듈 (store.py)

### 저장

```python
from app.embedding.store import store_documents

store_documents(chunks)
# 입력: list[Document]
# 동작: 임베딩 변환 후 code_embeddings 테이블에 INSERT
```

### 재인덱싱

Repo Sync 시 기존 벡터를 삭제하고 새로 저장한다.

```python
from app.embedding.store import reindex

reindex("proj_123", new_chunks)
# 동작:
# 1. project_id 기준으로 기존 벡터 DELETE
# 2. 새 청크 임베딩 후 INSERT
```

---

## metadata JSONB 구조

```json
{
  "source": "src/auth.ts",
  "language": "typescript",
  "extension": ".ts",
  "chunk_index": 0,
  "total_chunks": 5,
  "start_line": 1,
  "end_line": 30,
  "project_id": "proj_123"
}
```

---

## 혜수(검색)와의 연결 포인트

혜수는 `code_embeddings` 테이블에서 코사인 유사도 기반으로 검색한다.

```sql
-- 벡터 검색 예시
SELECT
  content,
  metadata,
  1 - (embedding <=> $1) AS score
FROM code_embeddings
WHERE project_id = $2
ORDER BY embedding <=> $1
LIMIT $3;

-- $1 = 질문 임베딩 벡터 (1536차원)
-- $2 = 프로젝트 ID
-- $3 = top-k (기본 5)
```

### 필터링 방식 합의 사항

- `project_id` 컬럼으로 프로젝트별 필터링
- 코사인 유사도 (`<=>` 연산자) 사용
- `metadata` JSONB에서 `source`, `language` 등 추가 필터링 가능

---

## 비용 추정

```
text-embedding-3-small 기준:
- 가격: $0.02 / 1M 토큰
- 청크 1개 평균 1000자 ≈ 250 토큰
- 파일 80개 × 청크 평균 5개 = 400 청크
- 400 × 250 = 100,000 토큰
- 비용: $0.002 (Repo Sync 1회당 약 0.2센트)
```
