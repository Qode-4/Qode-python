import os
import json
import psycopg
from dotenv import load_dotenv
from langchain_core.documents import Document
from app.embedding.embedder import embed_documents

load_dotenv()

def get_connection():
    return psycopg.connect(os.getenv("DATABASE_URL"))

def store_documents(chunks: list[Document]) -> None:
    vectors = embed_documents(chunks)
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            for chunk, vector in zip(chunks, vectors):
                cur.execute(
                    """
                    INSERT INTO code_embeddings 
                        (embedding, content, metadata, project_id)
                    VALUES 
                        (%s, %s, %s, %s)
                    """,
                    (
                        vector,
                        chunk.page_content,
                        json.dumps(chunk.metadata),
                        chunk.metadata["project_id"],
                    )
                )
        conn.commit()
    
    print(f"{len(chunks)}개 청크 저장 완료")

def reindex(project_id: str, new_chunks: list[Document]) -> None:
    # 1. 기존 벡터 삭제
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM code_embeddings WHERE project_id = %s",
                (project_id,)
            )
        conn.commit()
    print(f"{project_id} 기존 벡터 삭제 완료")

    # 2. 새 벡터 저장
    store_documents(new_chunks)
    print(f"{project_id} 재인덱싱 완료")