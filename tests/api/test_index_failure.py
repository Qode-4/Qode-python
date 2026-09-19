# 열린 과제 13-6. /index 가 실패하면 200 이 아니라 500 이어야 Node 가 알아챈다
from fastapi.testclient import TestClient

import app.api.main as main


def test_index_failure_returns_500(monkeypatch):
    def boom(_project_id):
        raise RuntimeError("repo missing")

    monkeypatch.setattr(main, "resolve_repo_path", boom)
    res = TestClient(main.app).post("/index", json={"projectId": "p1", "syncJobId": "j1"})
    assert res.status_code == 500
    body = res.json()["detail"]
    assert body["status"] == "failed"
    assert body["chunks_created"] == 0
    assert "repo missing" in body["error"]
