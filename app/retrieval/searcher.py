# searcher.py - pgvector, faiss에서 유사도 검색
import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document

load_dotenv()

TOP_K = int(os.getenv("RETRIEVAL_TOP_K", 5))

vectorstore = PGVector(
    embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
    collection_name=os.getenv("COLLECTION_NAME"),
    connection=os.getenv("DATABASE_URL"),
)

async def search(query: str, top_k: int = TOP_K) -> list[Document]:
    results = vectorstore.as_retriever(
        search_type="similarity",
        # search_type="similarity_score_threshold", # 비슷한 애들만 가져옴
        search_kwargs={"k": top_k},
    )

    # 유사도 metadata에 같이 넣어주기
    # r = await vectorstore.asimilarity_search_with_relevance_scores(
    #     query, k = top_k
    # )
    # for doc, score in results:
    #     doc.metadata["score"] = score

    # return [doc for doc, _ in results]

    return await results.ainvoke(query)