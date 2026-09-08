# 어떤 확장자 파일을 수집할지
# 어떤 폴더를 건너뛸지, 어떤 파일을 건너뛸지
# 확장자 -> 언어 매핑 (토큰 분할할 때 사용)
# 50자 미만 청크 제거
# 파일 수 많으면 경고

import os
from fnmatch import fnmatch
from langchain_core.documents import Document

## -- 상수 정의 --

# 허용 확장자: 이 확장자만 수집 
ALLOWED_EXTENSIONS = [
    ".ts", ".tsx", ".js", ".jsx", ".py", ".java", ".go", ".rs", ".rb",
    ".yml", ".yaml", ".json", ".sql",
]

# 제외 디렉터리: 통째로 건너뜀 
EXCLUDE_DIRS = [
    "node_modules", ".git", "dist", "build", ".next",
    "coverage", "__pycache__",
]

# 테스트 디렉터리: 제외하지 않고 is_test=True 로 표시만 함
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e"}

# 제외 파일 패턴 
EXCLUDE_PATTERNS = [
    ".env", ".env.*", "credentials.*",
    "*.lock", "package-lock.json",
    "*.min.js", "*.map",
]

# 테스트 파일 패턴: 제외하지 않고 is_test=True 로 표시만 함
TEST_PATTERNS = [
    "*.test.*", "*.spec.*",
    "test_*.py", "*_test.py", "conftest.py",
    "*_test.go", "*Test.java", "*Tests.java", "*_spec.rb",
]

# 확장자 → 언어 매핑 
EXTENSION_TO_LANGUAGE = {
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript",
    ".py": "python",     ".java": "java",
    ".go": "go",         ".rs": "rust",
    ".rb": "ruby",       ".md": "markdown",
    ".txt": "text",      ".json": "json",
    ".yml": "yaml",      ".yaml": "yaml",
    ".sql": "sql",
}

MIN_CHUNK_LENGTH = 50
FILE_COUNT_WARNING_THRESHOLD = 3000

## -- 필터링 함수 --

def detect_language(extension: str) -> str:
    # Dictionary에서 확장자에 해당하는 언어 반환 / 없으면 "unknown" 출력
    return EXTENSION_TO_LANGUAGE.get(extension, "unknown")

def is_allowed_file(filename:str) -> bool:
    # 파일을 수집할지 여부 판단 / 허용 확장자에 포함이 되어 있고, 제외 패턴에 안 걸리면 True 반환

    ext = os.path.splitext(filename)[1].lower() # 허용 확장자에 포함이 안 되면 False 반환
    if ext not in ALLOWED_EXTENSIONS:
        return False
    
    name = os.path.basename(filename) # 파일명만 추출    
    for pattern in EXCLUDE_PATTERNS: # 제외 패턴에 걸리면 False 반환
        if fnmatch(name, pattern): 
            return False
    return True

def is_test_file(relative_path: str) -> bool:
    # 테스트 코드 여부 판단 / 경로 내 테스트 디렉터리 또는 파일명 패턴 매칭
    parts = relative_path.replace("\\", "/").split("/")

    if any(part.lower() in TEST_DIRS for part in parts[:-1]):
        return True

    name = parts[-1]
    return any(fnmatch(name, pattern) for pattern in TEST_PATTERNS)

def filter_chunks(chunks: list[Document]) -> list[Document]: # 청크 리스트 받아서 필터링을 함
    # 지금은 일단 Min_Chunk_Length보다 짧은 청크 제거하는 필터만 구현 (추후에 더 추가할 수 있음)
    result = []

    for chunk in chunks:
        if len(chunk.page_content.strip()) >= MIN_CHUNK_LENGTH:
            result.append(chunk)
    return result