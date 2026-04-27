"""
Test suite for Features 1-6 of the AI-Augmented CI/CD System.
All tests run without external API keys using mock/fallback responses.

Authentication Note
-------------------
The server enforces X-API-Token when AI_REVIEW_SECRET is set.
The `client` fixture in conftest.py injects this header automatically,
so every test here gets a properly authenticated TestClient.
"""

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.gate import rule_based_evaluate
from app.schemas import GateRequest, FeedbackRequest
from app.utils import parse_llm_json, fallback_review
from app.prompt import build_prompt, MAX_DIFF_CHARS

# ---------------------------------------------------------------------------
# Sample diffs used across multiple tests
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Auth / Middleware tests (NEW)
# ---------------------------------------------------------------------------

class TestAuthentication:
    """Verify that the token_auth_middleware behaves correctly."""

    def test_health_no_auth_allowed(self):
        """Health endpoint must be reachable without any auth token."""
        bare_client = TestClient(app, raise_server_exceptions=True)
        resp = bare_client.get("/health")
        assert resp.status_code == 200, (
            f"Health check should bypass auth gate, got {resp.status_code}"
        )

    def test_protected_endpoint_without_token_returns_401(self):
        """Posting to /review without the token must be rejected when AI_REVIEW_SECRET is set."""
        secret = os.getenv("AI_REVIEW_SECRET", "")
        if not secret:
            pytest.skip("AI_REVIEW_SECRET not configured — auth middleware is inactive")

        bare_client = TestClient(app, raise_server_exceptions=False)
        resp = bare_client.post("/review", json={"repo": "r", "pr_id": 1, "diff": CLEAN_DIFF})
        assert resp.status_code == 401, (
            f"Expected 401 Unauthorized without token, got {resp.status_code}"
        )

    def test_protected_endpoint_with_correct_token_allowed(self, client):
        """Posting to /review with the correct X-API-Token must succeed (not 401)."""
        resp = client.post("/review", json={"repo": "r", "pr_id": 1, "diff": CLEAN_DIFF})
        assert resp.status_code != 401, (
            "Request was rejected — check that X-API-Token matches AI_REVIEW_SECRET"
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Feature 1: Code Review
# ---------------------------------------------------------------------------

class TestCodeReview:

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_review_version_in_health(self, client):
        resp = client.get("/health")
        body = resp.json()
        assert "version" in body, "Health response should include 'version'"

    def test_review_empty_diff_rejected(self, client):
        resp = client.post("/review", json={"repo": "r", "pr_id": 1, "diff": "   "})
        assert resp.status_code == 400

    def test_review_sql_low_score(self, client):
        resp = client.post("/review", json={"repo": "r", "pr_id": 1, "diff": SQL_DIFF})
        assert resp.status_code == 200
        body = resp.json()
        assert body["score"] <= 3.0
        assert any(i["severity"] == "critical" for i in body["issues"])

    def test_review_clean_high_score(self, client):
        resp = client.post("/review", json={"repo": "r", "pr_id": 2, "diff": CLEAN_DIFF})
        assert resp.status_code == 200
        assert resp.json()["score"] >= 7.0

    def test_review_schema(self, client):
        resp = client.post("/review", json={"repo": "r", "pr_id": 3, "diff": CLEAN_DIFF})
        body = resp.json()
        assert all(k in body for k in ("summary", "score", "issues", "strengths"))

    def test_review_score_in_range(self, client):
        """Score must always be between 0 and 10."""
        resp = client.post("/review", json={"repo": "r", "pr_id": 4, "diff": CLEAN_DIFF})
        score = resp.json()["score"]
        assert 0.0 <= score <= 10.0, f"Score {score} is out of range [0, 10]"

    def test_review_secret_diff_flagged(self, client):
        """A diff with hard-coded secrets should be flagged as critical."""
        resp = client.post("/review", json={"repo": "r", "pr_id": 5, "diff": SECRET_DIFF})
        assert resp.status_code == 200
        body = resp.json()
        severities = [i["severity"] for i in body["issues"]]
        assert "critical" in severities, (
            "Hard-coded secrets should raise at least one critical issue"
        )


# ---------------------------------------------------------------------------
# Feature 2: Quality Gate
# ---------------------------------------------------------------------------

def _gp(**kw):
    """Build a default gate payload, overriding with keyword args."""
    d = {"ai_score": 8.0, "issues": [], "test_coverage": 85.0, "lint_errors": 0}
    d.update(kw)
    return d


class TestQualityGate:

    def test_gate_pass(self, client):
        assert client.post("/evaluate", json=_gp()).json()["status"] == "PASS"

    def test_gate_fail_critical(self, client):
        issues = [{"severity": "critical", "type": "security", "title": "x",
                   "file": "f", "description": "d", "suggestion": "s"}]
        assert client.post("/evaluate", json=_gp(issues=issues)).json()["status"] == "FAIL"

    def test_gate_fail_low_score(self, client):
        assert client.post("/evaluate", json=_gp(ai_score=3.5)).json()["status"] == "FAIL"

    def test_gate_fail_lint(self, client):
        assert client.post("/evaluate", json=_gp(lint_errors=2)).json()["status"] == "FAIL"

    def test_gate_review_medium(self, client):
        assert (
            client.post("/evaluate", json=_gp(ai_score=6.0, test_coverage=70.0))
            .json()["status"] == "REVIEW"
        )

    def test_gate_schema(self, client):
        body = client.post("/evaluate", json=_gp()).json()
        assert all(k in body for k in ("status", "reasons", "confidence"))
        assert 0 <= body["confidence"] <= 1

    def test_gate_confidence_is_float(self, client):
        body = client.post("/evaluate", json=_gp()).json()
        assert isinstance(body["confidence"], float)

    # Rule-based unit tests (no HTTP)
    def test_rule_pass(self):
        req = GateRequest(ai_score=8.5, issues=[], test_coverage=90.0, lint_errors=0)
        assert rule_based_evaluate(req)[0] == "PASS"

    def test_rule_fail_critical(self):
        req = GateRequest(ai_score=8.5, issues=[{"severity": "critical"}],
                         test_coverage=90.0, lint_errors=0)
        assert rule_based_evaluate(req)[0] == "FAIL"

    def test_rule_review_coverage(self):
        req = GateRequest(ai_score=7.5, issues=[], test_coverage=70.0, lint_errors=0)
        assert rule_based_evaluate(req)[0] == "REVIEW"


# ---------------------------------------------------------------------------
# Feature 3: Multi-Agent Review
# ---------------------------------------------------------------------------

class TestMultiAgentReview:

    def test_multi_review_empty_rejected(self, client):
        assert client.post("/multi-review", json={"diff": ""}).status_code == 400

    def test_multi_review_sql_security(self, client):
        body = client.post("/multi-review", json={"diff": SQL_DIFF}).json()
        assert body["security"]["score"] <= 3.0
        assert any(i["severity"] == "critical" for i in body["security"]["issues"])

    def test_multi_review_schema(self, client):
        body = client.post("/multi-review", json={"diff": CLEAN_DIFF}).json()
        for k in ("code_quality", "security", "performance", "final_score"):
            assert k in body
        assert 0 <= body["final_score"] <= 10

    def test_multi_final_score_is_avg(self, client):
        body = client.post("/multi-review", json={"diff": CLEAN_DIFF}).json()
        exp = round(
            (body["code_quality"]["score"] + body["security"]["score"]
             + body["performance"]["score"]) / 3,
            2,
        )
        assert abs(body["final_score"] - exp) < 0.05

    def test_multi_review_agents_each_have_issues_key(self, client):
        body = client.post("/multi-review", json={"diff": SQL_DIFF}).json()
        for agent in ("code_quality", "security", "performance"):
            assert "issues" in body[agent], f"Agent '{agent}' response missing 'issues' key"


# ---------------------------------------------------------------------------
# Feature 4: Documentation Generator
# ---------------------------------------------------------------------------

class TestDocsGenerator:

    def test_docs_empty_rejected(self, client):
        assert client.post("/generate-docs", json={"diff": "  "}).status_code == 400

    def test_docs_schema(self, client):
        body = client.post("/generate-docs", json={"diff": CLEAN_DIFF}).json()
        for k in ("summary", "changelog", "api_changes", "developer_notes"):
            assert k in body

    def test_docs_has_entries(self, client):
        body = client.post("/generate-docs", json={"diff": CLEAN_DIFF}).json()
        assert body["summary"]
        assert len(body["changelog"]) > 0

    def test_docs_changelog_is_list(self, client):
        body = client.post("/generate-docs", json={"diff": CLEAN_DIFF}).json()
        assert isinstance(body["changelog"], list)
        assert isinstance(body["api_changes"], list)
        assert isinstance(body["developer_notes"], list)


# ---------------------------------------------------------------------------
# Feature 5: Logging / Observability
# ---------------------------------------------------------------------------

class TestObservability:

    def test_request_id_header(self, client):
        assert "x-request-id" in client.get("/health").headers

    def test_custom_request_id_echoed(self, client):
        resp = client.get("/health", headers={"X-Request-ID": "myid-123"})
        assert resp.headers.get("x-request-id") == "myid-123"

    def test_auto_generated_request_id_format(self, client):
        """Auto-generated request IDs should be non-empty strings."""
        rid = client.get("/health").headers.get("x-request-id", "")
        assert rid, "x-request-id header must not be empty"


# ---------------------------------------------------------------------------
# Feature 6: Feedback Loop
# ---------------------------------------------------------------------------

class TestFeedbackLoop:

    def test_feedback_accepted(self, client):
        body = client.post(
            "/feedback",
            json={"pr_id": 42, "accepted": True, "false_positive": False},
        ).json()
        assert body["status"] == "ok"
        assert body["feedback_id"]

    def test_feedback_false_positive(self, client):
        body = client.post(
            "/feedback",
            json={"pr_id": 43, "accepted": False, "false_positive": True,
                  "comments": "missed edge case"},
        ).json()
        assert body["status"] == "ok"

    def test_feedback_stats(self, client):
        body = client.get("/feedback/stats").json()
        assert "total" in body and "acceptance_rate" in body

    def test_feedback_acceptance_rate_in_range(self, client):
        rate = client.get("/feedback/stats").json().get("acceptance_rate", -1)
        assert 0.0 <= rate <= 1.0, f"acceptance_rate={rate} out of [0, 1]"

    def test_feedback_persistence(self, tmp_path, monkeypatch):
        import app.feedback as fb
        monkeypatch.setattr(fb, "FEEDBACK_STORE_PATH", tmp_path / "fb.json")
        req = FeedbackRequest(pr_id=99, accepted=True, false_positive=False)
        fid = fb.save_feedback(req)
        assert fid
        records = fb.get_all_feedback()
        assert len(records) == 1 and records[0]["pr_id"] == 99


# ---------------------------------------------------------------------------
# Pipeline (end-to-end)
# ---------------------------------------------------------------------------

class TestPipeline:

    def test_pipeline_sections(self, client):
        body = client.post(
            "/pipeline",
            json={"repo": "r", "pr_id": 1, "diff": CLEAN_DIFF},
        ).json()
        for k in ("review", "multi_agent_review", "quality_gate", "documentation"):
            assert k in body, f"Pipeline response missing key: '{k}'"

    def test_pipeline_sql_fails_gate(self, client):
        body = client.post(
            "/pipeline",
            json={"repo": "r", "pr_id": 2, "diff": SQL_DIFF},
        ).json()
        assert body["quality_gate"]["status"] == "FAIL"

    def test_pipeline_returns_repo_and_pr_id(self, client):
        body = client.post(
            "/pipeline",
            json={"repo": "my-org/my-repo", "pr_id": 77, "diff": CLEAN_DIFF},
        ).json()
        assert body.get("repo") == "my-org/my-repo"
        assert body.get("pr_id") == 77

    def test_pipeline_clean_diff_passes_gate(self, client):
        body = client.post(
            "/pipeline",
            json={"repo": "r", "pr_id": 3, "diff": CLEAN_DIFF},
        ).json()
        assert body["quality_gate"]["status"] in ("PASS", "REVIEW"), (
            f"Clean code should pass or request review, got {body['quality_gate']['status']}"
        )

    def test_pipeline_empty_diff_rejected(self, client):
        resp = client.post("/pipeline", json={"repo": "r", "pr_id": 4, "diff": "  "})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Utility unit tests (no HTTP)
# ---------------------------------------------------------------------------

class TestUtilities:

    def test_parse_json(self):
        assert parse_llm_json('{"score": 8.5}')["score"] == 8.5

    def test_parse_fenced(self):
        assert parse_llm_json('```json\n{"score": 7}\n```')["score"] == 7

    def test_parse_bad_raises(self):
        with pytest.raises(ValueError):
            parse_llm_json("not json!!!")

    def test_prompt_truncates(self):
        assert "truncated" in build_prompt("+" + "x" * (MAX_DIFF_CHARS + 2000))

    def test_fallback_review_returns_valid_schema(self):
        """fallback_review should return a dict with all required review keys."""
        result = fallback_review(SQL_DIFF)
        for key in ("summary", "score", "issues", "strengths"):
            assert key in result, f"fallback_review missing key: '{key}'"
