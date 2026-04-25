"""
Test suite for Features 1-6 of the AI-Augmented CI/CD System.
All tests run without external API keys using mock fallbacks.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.gate import rule_based_evaluate
from app.schemas import GateRequest, FeedbackRequest
from app.utils import parse_llm_json, fallback_review
from app.prompt import build_prompt, MAX_DIFF_CHARS

client = TestClient(app)

SQL_DIFF = '''diff --git a/app.py b/app.py
+++ b/app.py
@@ -0,0 +1,3 @@
+def get_user(id):
+    return db.query("SELECT * FROM users WHERE id=" + id)
'''

CLEAN_DIFF = '''diff --git a/utils.py b/utils.py
+++ b/utils.py
@@ -0,0 +1,6 @@
+def add(a: int, b: int) -> int:
+    return a + b
+
+def greet(name: str) -> str:
+    return f"Hello, {name}!"
'''

SECRET_DIFF = '''diff --git a/config.py b/config.py
+++ b/config.py
@@ -0,0 +1,2 @@
+password = "supersecret123"
+api_key = "sk-live-abc123"
'''

# Feature 1 tests
def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_review_empty_diff_rejected():
    resp = client.post("/review", json={"repo": "r", "pr_id": 1, "diff": "   "})
    assert resp.status_code == 400

def test_review_sql_low_score():
    resp = client.post("/review", json={"repo": "r", "pr_id": 1, "diff": SQL_DIFF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] <= 3.0
    assert any(i["severity"] == "critical" for i in body["issues"])

def test_review_clean_high_score():
    resp = client.post("/review", json={"repo": "r", "pr_id": 2, "diff": CLEAN_DIFF})
    assert resp.status_code == 200
    assert resp.json()["score"] >= 7.0

def test_review_schema():
    resp = client.post("/review", json={"repo": "r", "pr_id": 3, "diff": CLEAN_DIFF})
    body = resp.json()
    assert all(k in body for k in ("summary", "score", "issues", "strengths"))

# Feature 2 tests
def _gp(**kw):
    d = {"ai_score": 8.0, "issues": [], "test_coverage": 85.0, "lint_errors": 0}
    d.update(kw)
    return d

def test_gate_pass():
    assert client.post("/evaluate", json=_gp()).json()["status"] == "PASS"

def test_gate_fail_critical():
    issues = [{"severity": "critical", "type": "security", "title": "x", "file": "f", "description": "d", "suggestion": "s"}]
    assert client.post("/evaluate", json=_gp(issues=issues)).json()["status"] == "FAIL"

def test_gate_fail_low_score():
    assert client.post("/evaluate", json=_gp(ai_score=3.5)).json()["status"] == "FAIL"

def test_gate_fail_lint():
    assert client.post("/evaluate", json=_gp(lint_errors=2)).json()["status"] == "FAIL"

def test_gate_review_medium():
    assert client.post("/evaluate", json=_gp(ai_score=6.0, test_coverage=70.0)).json()["status"] == "REVIEW"

def test_gate_schema():
    body = client.post("/evaluate", json=_gp()).json()
    assert all(k in body for k in ("status", "reasons", "confidence"))
    assert 0 <= body["confidence"] <= 1

def test_rule_pass():
    req = GateRequest(ai_score=8.5, issues=[], test_coverage=90.0, lint_errors=0)
    assert rule_based_evaluate(req)[0] == "PASS"

def test_rule_fail_critical():
    req = GateRequest(ai_score=8.5, issues=[{"severity": "critical"}], test_coverage=90.0, lint_errors=0)
    assert rule_based_evaluate(req)[0] == "FAIL"

def test_rule_review_coverage():
    req = GateRequest(ai_score=7.5, issues=[], test_coverage=70.0, lint_errors=0)
    assert rule_based_evaluate(req)[0] == "REVIEW"

# Feature 3 tests
def test_multi_review_empty_rejected():
    assert client.post("/multi-review", json={"diff": ""}).status_code == 400

def test_multi_review_sql_security():
    body = client.post("/multi-review", json={"diff": SQL_DIFF}).json()
    assert body["security"]["score"] <= 3.0
    assert any(i["severity"] == "critical" for i in body["security"]["issues"])

def test_multi_review_schema():
    body = client.post("/multi-review", json={"diff": CLEAN_DIFF}).json()
    for k in ("code_quality", "security", "performance", "final_score"):
        assert k in body
    assert 0 <= body["final_score"] <= 10

def test_multi_final_score_is_avg():
    body = client.post("/multi-review", json={"diff": CLEAN_DIFF}).json()
    exp = round((body["code_quality"]["score"] + body["security"]["score"] + body["performance"]["score"]) / 3, 2)
    assert abs(body["final_score"] - exp) < 0.05

# Feature 4 tests
def test_docs_empty_rejected():
    assert client.post("/generate-docs", json={"diff": "  "}).status_code == 400

def test_docs_schema():
    body = client.post("/generate-docs", json={"diff": CLEAN_DIFF}).json()
    for k in ("summary", "changelog", "api_changes", "developer_notes"):
        assert k in body

def test_docs_has_entries():
    body = client.post("/generate-docs", json={"diff": CLEAN_DIFF}).json()
    assert body["summary"]
    assert len(body["changelog"]) > 0

# Feature 5 (logging/observability) tests
def test_request_id_header():
    assert "x-request-id" in client.get("/health").headers

def test_custom_request_id_echoed():
    resp = client.get("/health", headers={"X-Request-ID": "myid-123"})
    assert resp.headers.get("x-request-id") == "myid-123"

# Feature 6 tests
def test_feedback_accepted():
    body = client.post("/feedback", json={"pr_id": 42, "accepted": True, "false_positive": False}).json()
    assert body["status"] == "ok"
    assert body["feedback_id"]

def test_feedback_false_positive():
    body = client.post("/feedback", json={"pr_id": 43, "accepted": False, "false_positive": True, "comments": "missed edge case"}).json()
    assert body["status"] == "ok"

def test_feedback_stats():
    body = client.get("/feedback/stats").json()
    assert "total" in body and "acceptance_rate" in body

def test_feedback_persistence(tmp_path, monkeypatch):
    import app.feedback as fb
    monkeypatch.setattr(fb, "FEEDBACK_STORE_PATH", tmp_path / "fb.json")
    req = FeedbackRequest(pr_id=99, accepted=True, false_positive=False)
    fid = fb.save_feedback(req)
    assert fid
    records = fb.get_all_feedback()
    assert len(records) == 1 and records[0]["pr_id"] == 99

# Pipeline tests
def test_pipeline_sections():
    body = client.post("/pipeline", json={"repo": "r", "pr_id": 1, "diff": CLEAN_DIFF}).json()
    for k in ("review", "multi_agent_review", "quality_gate", "documentation"):
        assert k in body

def test_pipeline_sql_fails_gate():
    body = client.post("/pipeline", json={"repo": "r", "pr_id": 2, "diff": SQL_DIFF}).json()
    assert body["quality_gate"]["status"] == "FAIL"

# Utility tests
def test_parse_json():
    assert parse_llm_json('{"score": 8.5}')["score"] == 8.5

def test_parse_fenced():
    assert parse_llm_json('```json\n{"score": 7}\n```')["score"] == 7

def test_parse_bad_raises():
    with pytest.raises(ValueError):
        parse_llm_json("not json!!!")

def test_prompt_truncates():
    assert "truncated" in build_prompt("+" + "x" * (MAX_DIFF_CHARS + 2000))
