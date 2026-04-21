from fastapi import FastAPI
from pydantic import BaseModel
from app.retrieval.pipeline import search_pipeline

app = FastAPI()

class SearchRequest(BaseModel):
    query: str
    project_id: str
    top_k: int = 5

@app.post("/search")
async def search(req: SearchRequest):
    result = await search_pipeline(req.query, req.project_id, req.top_k)
    return {
        "chunks": [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in result["chunks"]
        ],
        "search_meta": result["search_meta"]
    }