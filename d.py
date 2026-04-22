# test_quick.py  ← 루트에 임시로 만들기
import asyncio
from app.retrieval.pipeline import search_pipeline

async def main():
    results = await search_pipeline("jwt token 검증", project_id="test_project", top_k=3)
    for doc in results["chunks"]:  # ← ["chunks"] 추가
        print("---")
        print(doc.page_content[:100])
        print(doc.metadata)

    print(results["search_meta"])  # 메타 정보도 출력

asyncio.run(main())