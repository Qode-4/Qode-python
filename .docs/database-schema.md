# 데이터베이스 스키마

## 인프라

- **DB**: Aurora PostgreSQL (15.x 이상, pgvector 지원)
- **접속**: `DATABASE_URL` 환경 변수
- **SSL**: 설정 가능 (require/disable/verify-full)
- **CA 인증서**: AWS RDS용 `global-bundle.pem` (필요 시)

## 기존 테이블 (Node.js 서버가 사용)

Python RAG 서비스가 직접 읽거나 쓰지 않지만, 같은 DB에 존재하는 테이블들.

| 테이블 | 용도 |
|--------|------|
| `users` | 사용자 계정 |
| `projects` | 프로젝트 메타데이터, Git URL, 초대 코드 |
| `project_members` | 프로젝트 멤버십 (OWNER/MEMBER) |
| `project_sync_jobs` | Git 동기화 큐, 진행 상태 |
| `project_analysis` | **CAG 캐시** — JSONB로 코드 요약 저장 (교체 대상) |
| `chats` | 채팅 세션 (PERSONAL/TEAM) |
| `messages` | 채팅 메시지 (USER/ASSISTANT/SYSTEM 역할) |
| `sources` | 메시지 출처 (file_path, line 범위) |

### project_analysis 테이블 (참고용)

현재 CAG가 사용하는 테이블. RAG로 전환 후에도 당분간 병행 가능.

```sql
-- 기존 CAG 캐시 구조 (참고)
-- status: 'building' | 'ready' | 'failed'
-- summary: JSONB {
--   project_overview, architecture[], core_modules[],
--   key_flows[], risks[], recommended_next_steps[]
-- }
```

## RAG용 새 테이블 (Python 서비스가 사용)

### code_embeddings — 벡터 저장소

```sql
-- pgvector 확장 설치
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE code_embeddings (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding   vector(1536),         -- OpenAI text-embedding-3-small 기준
  content     TEXT NOT NULL,         -- 원본 청크 텍스트
  metadata    JSONB NOT NULL,        -- 메타데이터
  project_id  VARCHAR(100) NOT NULL, -- 프로젝트 ID (projects 테이블과 대응)
  created_at  TIMESTAMP DEFAULT NOW(),
  updated_at  TIMESTAMP DEFAULT NOW()
);

-- HNSW 인덱스 (벡터 검색용, 검색 속도 우선)
CREATE INDEX idx_embedding_hnsw
  ON code_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- 프로젝트별 필터링용 인덱스
CREATE INDEX idx_project_id ON code_embeddings (project_id);

-- metadata JSONB 검색용 인덱스
CREATE INDEX idx_metadata ON code_embeddings USING gin (metadata);
```

### metadata JSONB 구조

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

## 벡터 검색 쿼리 예시

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

-- $1 = 질문 임베딩 벡터 (1536차원)
-- $2 = 프로젝트 ID
-- $3 = top-k (기본 5)
```

## 인덱스 타입 비교

| | IVFFlat | HNSW |
|---|---------|------|
| 빌드 속도 | 빠름 | 느림 |
| 검색 속도 | 보통 | 빠름 |
| 메모리 | 적음 | 많음 |
| 적합한 경우 | 데이터 적을 때 (1만 건 이하) | 데이터 많을 때 |

현재 HNSW를 기본으로 사용. 데이터가 적은 초기에는 IVFFlat도 충분.

## 재인덱싱

Repo Sync 시 해당 프로젝트의 기존 벡터를 삭제하고 새로 저장한다.

```sql
-- 프로젝트별 삭제
DELETE FROM code_embeddings WHERE project_id = $1;

-- 새 벡터 INSERT
INSERT INTO code_embeddings (embedding, content, metadata, project_id)
VALUES ($1, $2, $3, $4);
```
