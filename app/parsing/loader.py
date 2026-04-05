import logging
import os
from langchain_core.documents import Document
from app.parsing.filters import (
    is_allowed_file,detect_language,EXCLUDE_DIRS, EXCLUDE_PATTERNS,FILE_COUNT_WARNING_THRESHOLD
)

logger = logging.getLogger(__name__)

def collect_documents(repo_path: str, project_id: str, max_files: int | None = None) -> list[Document]:
    # 레포지토리 순회하며 허용된 파일을 수집, Document 객체로 변환
    docs: list[Document] = []
    

    for root, dirs, files in os.walk(repo_path):
        
        # 제외 디렉터리 진입 X
        # [:]에 해당하는 애들을 비우고, 오른쪽 리스트에 해당하는 애들로 채워넣는 방식
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS] 

        for file_name in files:

            # 허용된 파일인지 체크
            if not is_allowed_file(file_name):
                continue

            # 파일 수 초과하면 경고 메시지 출력 후 수집 중단
            if max_files is not None and len(docs) >= max_files:
                print(f"파일 수가 {max_files}개를 초과하여 수집을 중단합니다.")
                return docs
        

            file_path = os.path.join(root, file_name)
            # 절대 경로를 상대 경로로 변환
            relative_path = os.path.relpath(file_path, repo_path)

            # 파일 읽기 (바이너리 파일이나 읽기 실패 시 건너뜀)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError):
                logger.warning("파일 읽기 실패, 건너뜀: %s", relative_path)
                continue

            # Document 객체 생성
            ext = os.path.splitext(file_name)[1]
            docs.append(Document(
                page_content=content,
                metadata={
                    "source": relative_path,
                    "language": detect_language(ext), 
                    "extension": ext,
                    "file_size": os.path.getsize(file_path),
                    "project_id": project_id, 
                }
            ))

    if len(docs) > FILE_COUNT_WARNING_THRESHOLD:
        logger.warning("파일 수가 %d개로 %d개를 초과했습니다. (project_id=%s)", len(docs), FILE_COUNT_WARNING_THRESHOLD, project_id)

    return docs


