import asyncio
from datasets import Dataset
from app.eval.dataset import QA_PAIRS
from app.retrieval.pipeline import search_pipeline
from ragas import evaluate
from ragas.metrics import context_precision, context_recall

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
    })

async def run():
    dataset = await build_dataset()
    result = evaluate(
        dataset,
        metrics=[context_precision, context_recall]
    )

    print(result)

asyncio.run(run())