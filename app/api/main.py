import time

from fastapi import FastAPI
from pydantic import BaseModel
from app.config import APP_ENV, resolve_repo_path
from app.embedding.store import reindex
from app.parsing import parse_and_chunk
from app.retrieval.pipeline import search_pipeline

app = FastAPI()

class SearchRequest(BaseModel):
    query: str
    project_id: str
    top_k: int = 5


class IndexRequest(BaseModel):
    projectId: str
    syncJobId: str


@app.get("/health")
def health():
    return {
        "status": "ok",
    }


@app.post("/index")
def index(req: IndexRequest):
    start_time = time.time()

    try:
        repo_path = resolve_repo_path(req.projectId)
        chunks = parse_and_chunk(str(repo_path), req.projectId)
        reindex(req.projectId, chunks)

        response = {
            "status": "completed",
            "projectId": req.projectId,
            "syncJobId": req.syncJobId,
            "appEnv": APP_ENV,
            "repoPath": str(repo_path),
            "chunks_created": len(chunks),
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }
    except Exception as e:
        response = {
            "status": "failed",
            "projectId": req.projectId,
            "syncJobId": req.syncJobId,
            "appEnv": APP_ENV,
            "chunks_created": 0,
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "error": str(e),
        }

    print(response)
    return response


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
