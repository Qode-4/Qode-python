# 1. Retrieval 개요
- search -> filter -> dedup -> rerancker로 이어지는 검색 파이프라인
- 단계별 단위 테스트
- 검색 결과를 토대로 검색 품질 평가

# 2. 프로젝트 구조 
```
QODE-PYTHON/
├── app/
│   ├── api/
│   │   └── main.py          # FastAPI 서버 진입점
│   ├── embedding/           # 임베딩 처리 (예지 님)
│   ├── eval/
│   │   ├── dataset.py       # 평가용 QA 데이터셋 (QA_PAIRS)
│   │   ├── evaluatate.py    # 평가 로직
│   │   ├── metrics.py       # 평가 메트릭 정의
│   │   ├── run_eval_ragas.py # RAGAS 기반 Retrieval 평가 실행
│   │   └── run_eval.py      # 일반 평가 실행
│   ├── retrieval/
│   │   ├── pipeline.py      # 검색 파이프라인 메인 로직
│   │   ├── searcher.py      # 검색기
│   │   ├── reranker.py      # 재순위화
│   │   ├── dedup.py         # 중복 제거
│   │   └── filter.py        # 필터링
│   └── parsing/             # 문서 파싱 (채연 님)
└── tests/                   # 테스트 코드
```

# 3. 서버 실행 방법
### 서버 실행
```
uvicorn app.api.main:app --reload
```

### 접속 확인
- 서버: http://127.0.0.1:8000
- API 문서 (Swagger UI): http://127.0.0.1:8000/docs

# 4. API 사용법
### POST `/search`
검색 쿼리를 받아 관련 문서 청크를 반환

### Request Body
```json
{
  "query": "검색할 질문",
  "project_id": "test_project", # DB에 현재 저장된 프로젝트 이 파일 밖에 없음!
  "top_k": 5 
}
```

### Response
```json
{
  "chunks": [
    {
      "content": "검색된 문서 내용",
      "metadata": { ... }
    }
  ],
  "search_meta": { ... }
}
```

**chunks 필드 설명**
 
| 필드 | 설명 |
|------|------|
| `content` | 검색된 코드 또는 문서 내용 |
| `metadata.source` | 원본 파일 경로 |
| `metadata.start_line` | 청크 시작 줄 번호 |
| `metadata.end_line` | 청크 끝 줄 번호 |
| `metadata.chunk_index` | 해당 파일 내 청크 순서 (0부터 시작) |
| `metadata.total_chunks` | 해당 파일의 전체 청크 수 |
| `metadata.language` | 파일 언어 |
| `metadata.extension` | 파일 확장자 |
| `metadata.file_size` | 파일 크기 (bytes) |
| `metadata.project_id` | 프로젝트 ID |
| `metadata.score` | 검색 유사도 점수 (0~1, 높을수록 관련도 높음) |
 
**search_meta 필드 설명**
 
| 필드 | 설명 |
|------|------|
| `total_found` | 벡터 검색으로 찾은 전체 청크 수 |
| `after_filter` | 필터링 후 남은 청크 수 |
| `after_dedup` | 중복 제거 후 남은 청크 수 |
| `final` | 최종 반환된 청크 수 |
| `search_time_ms` | 검색 소요 시간 (밀리초) |

# 5. Retrieval 평가 (RAGAS)
### RAGAS란?
RAGAS(Retrieval Augmented Generation Assessment)는 RAG 파이프라인의 품질을 자동으로 평가해주는 오픈소스 라이브러리입니다.  
LLM을 활용해 검색된 문서가 얼마나 정확하고 충분한지를 수치로 측정합니다.
 
### 평가 흐름
 
```
QA_PAIRS (질문 + 정답)
        ↓
search_pipeline() 호출 → 청크 검색
        ↓
ContextPrecisionWithReference.ascore()  → 검색 정밀도 측정
ContextRecall.ascore()                  → 검색 재현율 측정
        ↓
점수 출력 (0.0 ~ 1.0)
```
 
1. `dataset.py`의 `QA_PAIRS`에서 질문과 정답을 가져옴
2. 각 질문을 `search_pipeline()`에 넣어 관련 청크를 검색
3. 검색된 청크와 정답을 RAGAS 메트릭에 넣어 점수 계산
4. 질문별 점수 및 전체 평균 출력

### 개요
- 담당: Retrieval 품질 평가
- 사용 라이브러리: ragas==0.4.3
- 평가 메트릭: ContextPrecisionWithReference, ContextRecall

### 평가 실행
```bash
python -m app.eval.run_eval_ragas
```

### 평가 구조
```python
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextPrecisionWithReference, ContextRecall

# LLM 설정
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
llm = llm_factory("gpt-4o-mini", client=client)

# 메트릭 초기화
precision_scorer = ContextPrecisionWithReference(llm=llm)
recall_scorer = ContextRecall(llm=llm)

# 각 QA쌍에 대해 ascore() 직접 호출
result = await precision_scorer.ascore(
    user_input=query,
    retrieved_contexts=contexts,
    reference=ground_truth
)
```

### 메트릭 설명
| 메트릭 | 설명 |
|--------|------|:-----------------:|
| `ContextPrecisionWithReference` | 검색된 청크 중 실제 유용한 비율 |
| `ContextRecall` | 정답에 필요한 내용이 검색됐는지 |

### QA 데이터셋 형식 (`dataset.py`)
```python
QA_PAIRS = [
    {
        "query": "질문",
        "ground_truth": "정답"
    },
    ...
]
```

## 7. 주의사항
- Python **3.14** 사용 중 → Pydantic V1 호환 경고가 뜨지만 동작에는 문제 없음
- 현재 DB에 저장된 청크가 3개밖에 없어서 ContextPrecision, ContextRecall 지표가 모두 1.0으로 나옴 → 청크 수가 충분히 늘어난 후 재평가 필요