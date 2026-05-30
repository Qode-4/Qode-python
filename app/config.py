import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "local")

LOCAL_REPO_STORAGE_ROOT = Path(os.getenv("LOCAL_REPO_STORAGE_ROOT", ".")).resolve()
PROD_REPO_STORAGE_ROOT = Path(os.getenv("PROD_REPO_STORAGE_ROOT", ".")).resolve()


def get_repo_storage_root() -> Path:
    if APP_ENV == "production":
        return PROD_REPO_STORAGE_ROOT
    return LOCAL_REPO_STORAGE_ROOT


def resolve_repo_path(project_id: str) -> Path:
    repo_root = get_repo_storage_root()
    project_repo_dir = (repo_root / project_id).resolve()
    repo_path = (project_repo_dir / "current").resolve()

    if not project_repo_dir.is_relative_to(repo_root) or not repo_path.is_relative_to(repo_root):
        raise ValueError("Resolved repo path is outside repo storage root")

    if not project_repo_dir.is_dir():
        raise FileNotFoundError(f"Project repo directory not found: {project_repo_dir}")

    if not repo_path.is_dir():
        raise FileNotFoundError(f"Current repo directory not found: {repo_path}")

    return repo_path
