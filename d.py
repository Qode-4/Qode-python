# test_quick.py  ← 루트에 임시로 만들기
import asyncio
from app.retrieval.searcher import search

async def main():
    results = await search("test")
    print(f"결과 수: {len(results)}")
    for doc in results:
        print("---")
        print(doc.page_content[:100])
        print(doc.metadata)

asyncio.run(main())