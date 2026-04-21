import asyncio
from datasets import Dataset
from app.eval.dataset import QA_PAIRS
from app.retrieval.pipeline import search_pipeline
from ragas import evaluate
from ragas.metrics import context_precision, context_recall, faithfulness, answer_relevance

async def build_dataset():
    questions, ground_truths, contexts = [], [], []

    for qa in QA_PAIRS:
        result = await search_pipeline(qa["query"])
        retrieved = result["chunks"]

        questions.append(qa["query"])
        ground_truths.append(qa["ground_truth"])
        contexts.append([doc.page_content for doc in retrieved])

    return Dataset.from_dict({
        "question": questions,
        "ground_truth": ground_truths,
        "contexts": contexts,
        "answer": answers, # LLM 답변 (현재 빈 문자열 - 해당 필드에 LLM 답변 넣으면 faithfulness와 answer_relevancy 자동 측정)
    })

async def run():
    dataset = await build_dataset()
    result = evaluate(
        dataset,
        metrics=[
            context_precision,
            context_recall,
            faithfulness,
            answer_relevance
        ]
    )

    print(result)

asyncio.run(run())