CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS code_embeddings (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding   vector(1536),
  content     TEXT NOT NULL,
  metadata    JSONB NOT NULL,
  project_id  VARCHAR(100) NOT NULL,
  created_at  TIMESTAMP DEFAULT NOW(),
  updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embedding_hnsw
  ON code_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_project_id
  ON code_embeddings (project_id);

CREATE INDEX IF NOT EXISTS idx_metadata
  ON code_embeddings USING gin (metadata);
