# 전통적인 방법의 retrieval 평가 방법
import asyncio
from app.retrieval.pipeline import search_pipeline
from app.eval.dataset import QA_PAIRS
from app.eval.metrics import recall_at_k, mrr

async def run():
    recall_scores, mrr_scores = [], []

    for qa in QA_PAIRS:
        result = await search_pipeline(qa["query"])
        retrieved = result["chunks"]

        recall_scores.append(recall_at_k(retrieved, qa["relevant_keywords"], k=5))
        mrr_scores.append(mrr(retrieved, qa["relevant_keywords"]))

        print(f"Q: {qa['query']}")
        print(f"    Recall@5: {recall_scores[-1]:.1f} | MRR: {mrr_scores[-1]:.3f}")

    print(f"\n===== 최종 결과 =====")
    print(f"Recall@5 : {sum(recall_scores)/len(recall_scores):.3f}")
    print(f"MRR      : {sum(mrr_scores)/len(mrr_scores):.3f}")
    print(f"총 쿼리  : {len(QA_PAIRS)}개")

asyncio.run(run())