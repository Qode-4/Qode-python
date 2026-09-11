# 수빈 — 질의응답 + LangSmith

> RAG 파이프라인의 네 번째 단계.
> 검색된 청크를 LLM에 전달하고 답변을 생성하는 역할 + 전체 파이프라인 평가.
> **TypeScript** (기존 Qode 서버) — Python RAG 서비스의 검색 API를 HTTP로 호출

---

## 목표

혜수의 Python RAG 서비스가 제공하는 검색 API를 호출해서 청크를 받고, 프롬프트를 조립하고, 기존 LLM/SSE 스트리밍과 연결한다. LangSmith로 전체 RAG 파이프라인을 추적하고 품질을 평가한다.

---

## 입력 인터페이스 (혜수의 Python 서비스에서 HTTP로 받는 것)

현재 Python RAG 서비스의 `POST /search` 응답은 원본 청크 본문을 `content`에 담고, 유사도 점수는 `metadata.score`에 담아준다. TypeScript 쪽에서는 이 raw 응답을 그대로 프롬프트에 쓰지 말고, 먼저 `normalizeSearchResult()`로 내부 표준 타입으로 변환해서 사용한다.

```typescript
// Python 서비스 POST /search 실제 응답 타입
interface PythonSearchResult {
  chunks: PythonRetrievedChunk[];
  search_meta: {
    total_found: number;
    after_filter?: number;
    after_dedup?: number;
    final?: number;
    search_time_ms: number;
    error?: string;
  };
}

interface PythonRetrievedChunk {
  content: string;
  metadata: {
    source: string;
    language: string;
    extension?: string;
    file_size?: number;
    project_id: string;
    chunk_index: number;
    total_chunks: number;
    start_line?: number;
    end_line?: number;
    score: number;
  };
}

// Node.js 내부에서 사용할 표준 타입
interface SearchResult {
  chunks: RetrievedChunk[];
  search_meta: PythonSearchResult["search_meta"];
}

interface RetrievedChunk {
  page_content: string;
  score: number;
  metadata: {
    source: string;
    language: string;
    chunk_index: number;
    start_line?: number;
    end_line?: number;
    project_id: string;
    extension?: string;
    file_size?: number;
    total_chunks?: number;
  };
}

function normalizeSearchResult(result: PythonSearchResult): SearchResult {
  return {
    search_meta: result.search_meta,
    chunks: result.chunks.map((chunk) => {
      const { score, ...metadata } = chunk.metadata;

      return {
        page_content: chunk.content,
        score,
        metadata,
      };
    }),
  };
}
```

---

## 작업 목록

### 1. Python RAG 서비스 호출 클라이언트

혜수의 Python 서비스를 HTTP로 호출하는 코드. 호출 함수는 Python의 raw 응답을 받은 뒤 내부 표준 타입으로 normalize해서 반환한다.

```typescript
const RAG_SERVICE_URL = process.env.RAG_SERVICE_URL || "http://localhost:8000";

async function searchChunksRaw(
  query: string,
  projectId: string,
  topK: number = 5
): Promise<PythonSearchResult> {
  const response = await fetch(`${RAG_SERVICE_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      project_id: projectId,
      top_k: topK,
    }),
  });

  if (!response.ok) {
    throw new Error(`RAG 검색 실패: ${response.status}`);
  }

  return response.json();
}

async function searchChunks(
  query: string,
  projectId: string,
  topK: number = 5
): Promise<SearchResult> {
  const raw = await searchChunksRaw(query, projectId, topK);
  return normalizeSearchResult(raw);
}
```

### 2. prompt template 설계

기존 CAG 프롬프트를 RAG 방식으로 전환한다.

```typescript
// 기존 CAG 방식 (참고)
// 시스템 프롬프트 = "너는 코드 어시스턴트야"
//                + 분석 캐시 전체 (요약된 코드베이스)
//                + 최근 채팅 20개
//                + 사용자 질문

// RAG 방식
function buildRAGPrompt(
  searchResult: SearchResult,
  userQuestion: string,
  chatHistory: Message[]
): string {
  const contextBlock = searchResult.chunks
    .map(chunk => {
      const { source, start_line, end_line } = chunk.metadata;
      const lineInfo = start_line ? ` (L${start_line}-${end_line})` : "";
      return `--- ${source}${lineInfo} ---\n${chunk.page_content}`;
    })
    .join("\n\n");

  return `너는 Qode의 코드 어시스턴트다.
아래 참고 코드만 근거로 답변하고, 알 수 없는 내용은 추측하지 말고 모른다고 말한다.
답변에는 관련 파일 경로와 라인 범위를 함께 포함한다.

참고 코드:
${contextBlock}

질문: ${userQuestion}`;
}
```

**결정할 것:**
- 프롬프트 템플릿 구조 (시스템 프롬프트 / 코드 컨텍스트 / 질문의 순서)
- 출처 표시를 프롬프트에서 지시할지, 후처리로 붙일지
- 최근 채팅 히스토리를 어떻게 함께 넣을지

**주의할 것:**
- 프롬프트 조립은 반드시 `normalizeSearchResult()` 이후의 `SearchResult` 기준으로 한다.
- Python raw 응답의 `content`, `metadata.score`를 직접 여러 곳에서 참조하지 않는다. raw 응답 형태가 바뀌어도 adapter만 고치면 되게 만든다.

### 3. context 길이 조절

검색된 청크를 전부 넣으면 토큰 제한에 걸릴 수 있다.

```typescript
function trimContext(
  chunks: RetrievedChunk[],
  maxChars: number = 8000
): RetrievedChunk[] {
  const result: RetrievedChunk[] = [];
  let totalChars = 0;

  for (const chunk of chunks) {
    if (totalChars + chunk.page_content.length > maxChars) break;
    result.push(chunk);
    totalChars += chunk.page_content.length;
  }

  return result;
}
```

**결정할 것:**
- context 최대 길이 (토큰 비용 vs 답변 품질 트레이드오프)
- 청크 수 기준으로 자를지, 글자 수 기준으로 자를지

### 4. answer formatting

LLM 응답에 출처 정보를 포함시킨다.

```typescript
interface RAGResponse {
  answer: string;
  sources: SourceInfo[];
}

interface SourceInfo {
  filePath: string;
  lineRange?: string;
  relevanceScore: number;
}

function formatResponse(
  llmAnswer: string,
  searchResult: SearchResult
): RAGResponse {
  const sources = searchResult.chunks.map(chunk => ({
    filePath: chunk.metadata.source,
    lineRange: chunk.metadata.start_line
      ? `L${chunk.metadata.start_line}-${chunk.metadata.end_line}`
      : undefined,
    relevanceScore: chunk.score,
  }));

  const uniqueSources = deduplicateSources(sources);

  return {
    answer: llmAnswer,
    sources: uniqueSources,
  };
}
```

`deduplicateSources()`는 같은 파일/라인 범위가 여러 번 들어오면 가장 높은 점수 하나만 남긴다.

```typescript
function deduplicateSources(sources: SourceInfo[]): SourceInfo[] {
  const byKey = new Map<string, SourceInfo>();

  for (const source of sources) {
    const key = `${source.filePath}:${source.lineRange ?? ""}`;
    const existing = byKey.get(key);

    if (!existing || source.relevanceScore > existing.relevanceScore) {
      byKey.set(key, source);
    }
  }

  return [...byKey.values()];
}
```

### 5. 기존 LLM/SSE 연결

기존 Qode의 LLM 호출 + SSE 스트리밍 코드에 RAG 프롬프트를 연결한다.

```typescript
// 기존 CAG 코드 (수정 전)
async function handleChat(question: string, projectId: string) {
  const cache = await getAnalysisCache(projectId);     // 요약 캐시 조회
  const history = await getRecentMessages(chatRoomId);  // 최근 채팅
  const prompt = buildCAGPrompt(cache, question, history);
  return streamLLMResponse(prompt);
}

// RAG 코드 (수정 후)
async function handleChat(question: string, projectId: string) {
  // Python RAG 서비스 HTTP 호출 + normalize
  const searchResult = await searchChunks(question, projectId, 5);

  const history = await getRecentMessages(chatRoomId);
  const trimmed = trimContext(searchResult.chunks, 8000);
  const prompt = buildRAGPrompt(
    { ...searchResult, chunks: trimmed },
    question,
    history
  );
  const llmAnswer = await streamLLMResponse(prompt);
  return formatResponse(llmAnswer, searchResult);
}
```

**핵심:**
- 기존 `getAnalysisCache()` → `searchChunks()` (Python 서비스 HTTP 호출)로 교체
- 기존 `buildCAGPrompt()` → `buildRAGPrompt()` 로 교체
- 기존 `streamLLMResponse()` 는 그대로 사용
- Python 응답 형태 차이는 `normalizeSearchResult()`에서만 처리

### 6. LangSmith 연동

전체 RAG 파이프라인을 추적하고 품질을 평가한다.

#### 셋업

```typescript
// .env
// LANGCHAIN_TRACING_V2=true
// LANGCHAIN_API_KEY=ls__xxxx
// LANGCHAIN_PROJECT=qode-rag

// LangSmith JS SDK 사용
import { Client } from "langsmith";
import { traceable } from "langsmith/traceable";

const client = new Client();
```

#### 수동 트레이싱

```typescript
// 검색 단계 추적 (Python 서비스 호출 포함)
const tracedSearch = traceable(
  async (query: string, projectId: string) => {
    return await searchChunks(query, projectId, 5);
  },
  { name: "rag-search", run_type: "retriever" }
);

// 전체 파이프라인 추적
const tracedRAGPipeline = traceable(
  async (question: string, projectId: string) => {
    const searchResult = await tracedSearch(question, projectId);
    const prompt = buildRAGPrompt(searchResult, question, []);
    const answer = await streamLLMResponse(prompt);
    return formatResponse(answer, searchResult);
  },
  { name: "rag-pipeline", run_type: "chain" }
);
```

#### LangSmith에서 볼 수 있는 것

```
LangSmith 대시보드:
├ 각 질문별 전체 파이프라인 trace
│  ├ 검색 단계: Python 서비스 호출 시간, 반환된 청크, 유사도 점수
│  ├ 검색 메타: total_found, after_filter, after_dedup, final
│  ├ 프롬프트: 실제 조립된 프롬프트 전문
│  ├ LLM 호출: 토큰 사용량, 응답 시간
│  └ 최종 응답
├ 비용 추적 (토큰 사용량 기반)
└ 품질 평가 (아래 7번)
```

### 7. LangSmith 평가 (Evaluation)

```typescript
import { evaluate } from "langsmith/evaluation";

// 평가용 데이터셋 생성
const dataset = await client.createDataset("qode-rag-eval");

// 테스트 케이스 추가
await client.createExamples({
  datasetId: dataset.id,
  inputs: [
    { question: "인증 로직이 어디에 있어?" },
    { question: "데이터베이스 연결은 어떻게 해?" },
    { question: "라우팅 구조 설명해줘" },
  ],
  outputs: [
    { expected_sources: ["src/auth.ts"] },
    { expected_sources: ["src/config/database.ts"] },
    { expected_sources: ["src/routes/index.ts"] },
  ],
});

// 평가 실행
await evaluate(
  async (input) => {
    return await tracedRAGPipeline(input.question, "test-project");
  },
  {
    data: "qode-rag-eval",
    evaluators: [
      (run, example) => ({
        key: "source_included",
        score: run.outputs.sources.some(
          s => example.outputs.expected_sources.includes(s.filePath)
        ) ? 1 : 0,
      }),
      (run) => ({
        key: "answer_length",
        score: run.outputs.answer.length > 50 ? 1 : 0,
      }),
    ],
  }
);
```

---

## 병렬 작업

채연, 예지, 혜수와 **병렬 가능**하다.

수빈은 mock Python 응답과 normalized SearchResult로 프롬프트 설계와 LangSmith 셋업을 먼저 할 수 있다:

```typescript
// mock PythonSearchResult (실제 Python API 응답 형태)
const mockPythonSearchResult: PythonSearchResult = {
  chunks: [
    {
      content: "export function verifyToken(token: string) {\n  return jwt.verify(token, SECRET);\n}",
      metadata: {
        source: "src/auth.ts",
        language: "typescript",
        extension: ".ts",
        file_size: 2048,
        chunk_index: 0,
        total_chunks: 5,
        start_line: 12,
        end_line: 15,
        project_id: "test",
        score: 0.92,
      },
    },
  ],
  search_meta: {
    total_found: 5,
    after_filter: 5,
    after_dedup: 1,
    final: 1,
    search_time_ms: 45,
  },
};

// 이걸로 프롬프트 설계 + answer formatting 테스트
const mockSearchResult = normalizeSearchResult(mockPythonSearchResult);
const prompt = buildRAGPrompt(mockSearchResult, "인증 로직 어디에 있어?", []);
console.log(prompt);
```

## 개발 시작 순서

1. `PythonSearchResult`, `SearchResult`, `RetrievedChunk`, `SourceInfo` 타입을 만든다.
2. `searchChunksRaw()`로 Python `/search`를 호출한다.
3. `normalizeSearchResult()`로 `content`와 `metadata.score`를 내부 표준 타입의 `page_content`, `score`로 변환한다.
4. 이후 모든 프롬프트/출처/트레이싱 코드는 normalized `SearchResult`만 사용한다.
5. 실제 API 연결 전에는 `mockPythonSearchResult`로 `buildRAGPrompt()`, `trimContext()`, `formatResponse()`를 먼저 테스트한다.
6. LangSmith trace에는 검색 결과뿐 아니라 `search_meta.total_found`, `after_filter`, `after_dedup`, `final`, `search_time_ms`도 함께 남긴다.

---

## 전체 피드백 루프에서의 역할

수빈은 **최종 출력을 보는 사람**이라 전체 파이프라인의 문제를 먼저 발견할 수 있다:

```
수빈: LangSmith에서 답변 품질 확인
  │
  ├ 검색 결과가 관련 없음 → 혜수에게: "threshold 올려야 할 것 같아요"
  ├ 관련 청크는 맞는데 너무 작음 → 채연에게: "chunk_size 늘려야 할 것 같아요"
  ├ 임베딩 품질 자체가 낮음 → 예지에게: "모델을 large로 바꿔볼까요?"
  └ 프롬프트 구조 문제 → 수빈 본인이 수정
```

---

## 타임라인

| 주차 | 작업 | 비고 |
|------|------|------|
| Week 1 | prompt template 초안 설계 + Python 서비스 호출 클라이언트 구현 | mock PythonSearchResult와 adapter로 실험 |
| Week 1-2 | context 길이 조절 로직 + answer formatting | |
| Week 2 | LangSmith 셋업 (환경 변수, 프로젝트 생성) | |
| Week 3 | 혜수의 Python 검색 API와 연결 | 실제 응답을 normalize한 뒤 프롬프트 테스트 |
| Week 3-4 | 기존 LLM/SSE 코드에 RAG 프롬프트 연결 | CAG → RAG 전환 핵심 |
| Week 4 | LangSmith 트레이싱 + 평가 데이터셋 구축 | |
| Week 4-5 | 전체 파이프라인 평가 + 피드백 루프 | 전원 협업 |
