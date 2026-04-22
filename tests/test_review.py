import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils import parse_llm_json, fallback_review
from app.prompt import build_prompt, MAX_DIFF_CHARS

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SQL_INJECTION_DIFF = '''diff --git a/app.py b/app.py
index 0000000..1111111 100644
--- a/app.py
+++ b/app.py
@@ -0,0 +1,3 @@
+def get_user(id):
+    return db.query("SELECT * FROM users WHERE id=" + id)
'''

CLEAN_DIFF = '''diff --git a/utils.py b/utils.py
index 0000000..1111111 100644
--- a/utils.py
+++ b/utils.py
@@ -0,0 +1,6 @@
+def add(a: int, b: int) -> int:
+    """Return the sum of two integers."""
+    return a + b
+
+def greet(name: str) -> str:
+    return f"Hello, {name}!"
'''

SECRET_DIFF = '''diff --git a/config.py b/config.py
+++ b/config.py
@@ -0,0 +1,2 @@
+password = "supersecret123"
+api_key = "sk-real-key-here"
'''


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /review endpoint — input validation
# ---------------------------------------------------------------------------

def test_empty_diff_rejected():
    resp = client.post("/review", json={"repo": "myrepo", "pr_id": 1, "diff": "   "})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_missing_fields_rejected():
    resp = client.post("/review", json={"repo": "myrepo"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /review endpoint — mock LLM (no API key needed)
# ---------------------------------------------------------------------------

def test_sql_injection_diff_flagged():
    resp = client.post("/review", json={"repo": "testrepo", "pr_id": 1, "diff": SQL_INJECTION_DIFF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] <= 3.0, "SQL injection should result in a low score"
    types = [i["type"] for i in body["issues"]]
    assert "security" in types
    severities = [i["severity"] for i in body["issues"]]
    assert "critical" in severities


def test_clean_diff_high_score():
    resp = client.post("/review", json={"repo": "testrepo", "pr_id": 2, "diff": CLEAN_DIFF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] >= 7.0, "Clean code should score high"


def test_secret_diff_critical():
    resp = client.post("/review", json={"repo": "testrepo", "pr_id": 3, "diff": SECRET_DIFF})
    assert resp.status_code == 200
    body = resp.json()
    assert any(i["severity"] == "critical" for i in body["issues"])


def test_response_schema_valid():
    resp = client.post("/review", json={"repo": "testrepo", "pr_id": 4, "diff": CLEAN_DIFF})
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body
    assert "score" in body
    assert isinstance(body["score"], float)
    assert 0 <= body["score"] <= 10
    assert "issues" in body
    assert "strengths" in body


# ---------------------------------------------------------------------------
# Utility: parse_llm_json
# ---------------------------------------------------------------------------

def test_parse_clean_json():
    raw = '{"summary": "ok", "score": 8.5, "issues": [], "strengths": []}'
    result = parse_llm_json(raw)
    assert result["score"] == 8.5


def test_parse_markdown_fenced_json():
    raw = '```json\n{"summary": "ok", "score": 7.0, "issues": [], "strengths": []}\n```'
    result = parse_llm_json(raw)
    assert result["score"] == 7.0


def test_parse_json_with_surrounding_text():
    raw = 'Here is my review:\n{"summary":"s","score":5,"issues":[],"strengths":[]}\nDone.'
    result = parse_llm_json(raw)
    assert result["summary"] == "s"


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError):
        parse_llm_json("this is not json at all !!!!")


# ---------------------------------------------------------------------------
# Utility: fallback_review
# ---------------------------------------------------------------------------

def test_fallback_review_structure():
    fb = fallback_review()
    assert fb["score"] == 0.0
    assert fb["issues"] == []
    assert fb["strengths"] == []


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def test_prompt_contains_diff():
    diff = "diff --git a/foo.py b/foo.py\n+x = 1"
    prompt = build_prompt(diff)
    assert diff in prompt


def test_prompt_truncates_long_diff():
    long_diff = "+" + "x" * (MAX_DIFF_CHARS + 5000)
    prompt = build_prompt(long_diff)
    assert "truncated" in prompt
