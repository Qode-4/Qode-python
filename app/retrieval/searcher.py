# searcher.py
import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document

load_dotenv()

TOP_K = int(os.getenv("RETRIEVAL_TOP_K", 5))

vectorstore = PGVector(
    embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
    collection_name=os.getenv("COLLECTION_NAME", "chunks"),
    connection=os.getenv("PG_CONNECTION"),
)

async def search(query: str, top_k: int = TOP_K) -> list[Document]:
    retriever = vectorstore.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": top_k},
    )
    return await retriever.ainvoke(query)