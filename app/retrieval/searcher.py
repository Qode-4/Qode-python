# searcher.py
import os
import json
import psycopg
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from app.embedding.embedder import embed_query

load_dotenv(override=True)

def get_connection():
    return psycopg.connect(os.getenv("DATABASE_URL"))

class CodeRetriever(BaseRetriever):
    project_id: str
    top_k: int = 5

    def _get_relevant_documents(self, query: str) -> list[Document]:
        query_vector = embed_query(query)
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content, metadata,
                           1 - (embedding <=> %s::vector) AS score
                    FROM code_embeddings
                    WHERE project_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (query_vector, self.project_id, query_vector, self.top_k)
                )
                rows = cur.fetchall()
        
        return [
            Document(
                page_content=row[0],
                metadata={**row[1], "score": row[2]}
            )
            for row in rows
        ]

def search(query: str, project_id: str, top_k: int) -> list[Document]:
    retriever = CodeRetriever(project_id=project_id, top_k=top_k)
    return retriever.invoke(query)