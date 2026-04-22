import asyncio
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextPrecisionWithReference, ContextRecall
from app.eval.dataset import QA_PAIRS
from app.retrieval.pipeline import search_pipeline
import os

async def run():
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    llm = llm_factory("gpt-4o-mini", client=client)

    precision_scorer = ContextPrecisionWithReference(llm=llm)
    recall_scorer = ContextRecall(llm=llm)

    results = []

    for qa in QA_PAIRS:
        result = await search_pipeline(qa["query"], project_id="test_project", top_k=5)
        retrieved = result["chunks"]
        contexts = [doc.page_content for doc in retrieved]

        precision = await precision_scorer.ascore(
            user_input=qa["query"],
            retrieved_contexts=contexts,
            reference=qa["ground_truth"]
        )

        recall = await recall_scorer.ascore(
            user_input=qa["query"],
            retrieved_contexts=contexts,
            reference=qa["ground_truth"]
        )

        results.append({
            "query": qa["query"],
            "context_precision": precision.value,
            "context_recall": recall.value,
        })

        print(f"Q: {qa['query']}")
        print(f"  precision: {precision.value:.3f}")
        print(f"  recall:    {recall.value:.3f}")

    # 평균 출력
    avg_precision = sum(r["context_precision"] for r in results) / len(results)
    avg_recall = sum(r["context_recall"] for r in results) / len(results)
    print(f"\n=== 평균 ===")
    print(f"Context Precision: {avg_precision:.3f}")
    print(f"Context Recall:    {avg_recall:.3f}")

asyncio.run(run())