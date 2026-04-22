import os
import time
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

load_dotenv()

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=os.getenv("OPENAI_API_KEY"),
)

def embed_documents(chunks: list[Document], batch_size: int = 100) -> list[list[float]]:
    all_vectors = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.page_content for c in batch]

        try:
            vectors = embeddings.embed_documents(texts)
            all_vectors.extend(vectors)
        except Exception as e:
            if "rate_limit" in str(e).lower():
                print("Rate limit 초과, 60초 대기 후 재시도...")
                time.sleep(60)
                vectors = embeddings.embed_documents(texts)
                all_vectors.extend(vectors)
            else:
                raise

        print(f"임베딩 진행: {min(i + batch_size, len(chunks))}/{len(chunks)}")

    return all_vectors

def embed_query(query: str) -> list[float]:
    return embeddings.embed_query(query)