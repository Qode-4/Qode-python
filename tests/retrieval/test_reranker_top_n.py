# 열린 과제 13-19 후속 — 리랭커가 top_k 만큼 돌려줘야 top_k 상향이 LLM 에 닿는다
from langchain_core.documents import Document

import app.retrieval.reranker as reranker_module
from app.retrieval.reranker import rerank


class _CohereLike:
    """langchain_cohere.CohereRerank 흉내 — top_n(기본 3)개만 돌려준다."""

    top_n = 3

    def compress_documents(self, documents, query):
        ranked = sorted(documents, key=lambda d: d.metadata["score"])  # 벡터 점수 역순으로 뒤집어 재정렬을 흉내
        for d in ranked:
            d.metadata["relevance_score"] = 0.9
        return ranked[: self.top_n]


def docs(n):
    return [Document(page_content=f"chunk {i}", metadata={"score": i / 10}) for i in range(n)]


def test_rerank_returns_top_k_not_cohere_default_three(monkeypatch):
    monkeypatch.setattr(reranker_module, "RERANKER_ENABLED", True)
    monkeypatch.setattr(reranker_module, "_get_reranker", lambda: _CohereLike())

    result = rerank("q", docs(9), top_k=10)

    assert len(result) == 9, "Cohere 기본 top_n=3 에 잘리면 top_k 상향이 무의미하다"
    assert result[0].page_content == "chunk 0", "리랭커의 순서를 따라야 한다"
    assert all("rerank_score" in d.metadata for d in result)


def test_rerank_slices_to_top_k(monkeypatch):
    monkeypatch.setattr(reranker_module, "RERANKER_ENABLED", True)
    monkeypatch.setattr(reranker_module, "_get_reranker", lambda: _CohereLike())
    assert len(rerank("q", docs(9), top_k=5)) == 5
