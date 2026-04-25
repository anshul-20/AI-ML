# AI-Augmented CI/CD System

A production-ready, modular backend that wraps your entire PR review pipeline in AI — **100% powered by OpenAI GPT**. Six features, one API key.

---

## Features

| # | Feature | Endpoint | AI Model |
|---|---------|----------|----------|
| 1 | AI Code Review Agent | `POST /review` | GPT-4.1-mini |
| 2 | AI Quality Gate Engine | `POST /evaluate` | GPT-4.1-mini + rules |
| 3 | Multi-Agent AI Review | `POST /multi-review` | 3× GPT-4.1-mini (concurrent) |
| 4 | Documentation Generator | `POST /generate-docs` | GPT-4.1-mini |
| 5 | Observability & Logging | built-in middleware | — |
| 6 | Feedback Loop System | `POST /feedback` | — |
| — | Full Pipeline | `POST /pipeline` | All of the above |

---

## Project Structure

```
ai-code-review-agent/
├── app/
│   ├── main.py            # FastAPI app — all endpoints
│   ├── reviewer.py        # Feature 1: Full GPT code review
│   ├── gate.py            # Feature 2: Quality gate (rule + GPT)
│   ├── multi_agent.py     # Feature 3: 3 specialized GPT agents
│   ├── docs_generator.py  # Feature 4: Changelog & API docs
│   ├── feedback.py        # Feature 6: Feedback persistence
│   ├── openai_client.py   # Shared async OpenAI client (all features)
│   ├── logger.py          # Feature 5: Structured logging + request ID
│   ├── prompt.py          # Review prompt template + diff truncation
│   ├── schemas.py         # All Pydantic request/response models
│   └── utils.py           # JSON parsing helpers
├── tests/
│   └── test_review.py     # 30+ test cases (no API key needed)
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Quick Start

```bash
pip install -r requirements.txt

# One key powers everything
export OPENAI_API_KEY=sk-...

uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for the full interactive Swagger UI.

> **No API key?** All endpoints still work using smart heuristic mocks that detect SQL injection, hardcoded secrets, missing type hints, and more.

---

## API Examples

### Feature 1 — Code Review

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "my-service",
    "pr_id": 42,
    "diff": "diff --git a/app.py b/app.py\n+++ b/app.py\n+def get_user(id):\n+    return db.query(\"SELECT * FROM users WHERE id=\" + id)"
  }'
```

**Response:**
```json
{
  "summary": "Critical SQL injection vulnerability detected. Immediate fix required.",
  "score": 2.0,
  "issues": [{
    "type": "security",
    "severity": "critical",
    "file": "app.py",
    "line": null,
    "title": "SQL Injection Vulnerability",
    "description": "String concatenation in SQL query allows injection attacks.",
    "suggestion": "Use parameterized queries: db.query('SELECT * FROM users WHERE id = %s', (id,))"
  }],
  "strengths": []
}
```

### Feature 2 — Quality Gate

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{"ai_score": 7.2, "issues": [], "test_coverage": 78, "lint_errors": 0}'
```

### Feature 3 — Multi-Agent Review

```bash
curl -X POST http://localhost:8000/multi-review \
  -H "Content-Type: application/json" \
  -d '{"diff": "... git diff ..."}'
```

### Feature 4 — Generate Docs

```bash
curl -X POST http://localhost:8000/generate-docs \
  -H "Content-Type: application/json" \
  -d '{"diff": "... git diff ..."}'
```

### Feature 6 — Submit Feedback

```bash
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{"pr_id": 42, "accepted": true, "false_positive": false, "comments": "Great review"}'
```

### Full Pipeline — One call, all features

```bash
curl -X POST http://localhost:8000/pipeline \
  -H "Content-Type: application/json" \
  -d '{"repo": "my-service", "pr_id": 42, "diff": "... git diff ..."}'
```

---

## Quality Gate Logic (Feature 2)

| Condition | Decision |
|-----------|----------|
| Critical issue OR score < 5 OR lint_errors > 0 | **FAIL** |
| Score 5–7 OR coverage < 80% OR high severity issue | **REVIEW** |
| Score > 7, no high/critical, coverage ≥ 80% | **PASS** |

GPT provides human-readable reasoning for the decision. Rules always win on FAIL.

---

## Multi-Agent Architecture (Feature 3)

Three agents run **concurrently** via `asyncio.gather`:

| Agent | Focus |
|-------|-------|
| Code Quality | Readability, DRY, naming, structure, complexity |
| Security | OWASP Top 10, injection, secrets, auth |
| Performance | N+1 queries, O(n²) loops, memory leaks |

`final_score = average(quality, security, performance)`

---

## Observability (Feature 5)

Every request carries a correlation ID (`X-Request-ID`) through all log lines:

```
2025-01-01T12:00:00 | INFO | [a3f2c1b0] | app.main  | event=http_request | path=/review | status=200 | latency_ms=142
2025-01-01T12:00:00 | INFO | [a3f2c1b0] | app.openai_client | event=openai_call | status=ok | latency_ms=980 | tokens=412
```

Pass your own ID: `curl -H "X-Request-ID: pr-42-trace" ...`

---

## Feedback Store (Feature 6)

Stored to `feedback_store.json` by default. Override:

```bash
export FEEDBACK_STORE=/path/to/store.json
```

View analytics:
```bash
curl http://localhost:8000/feedback/stats
# {"total": 42, "accepted": 38, "rejected": 4, "acceptance_rate": 0.9, "false_positive_rate": 0.05}
```

---

## Running Tests

```bash
pytest tests/ -v
```

**All 30+ tests pass without an API key** using the built-in mock engine.

---

## Docker

```bash
docker build -t ai-cicd-system .
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... ai-cicd-system
```

---

## Score Reference

| Score | Meaning |
|-------|---------|
| 9–10 | Production-ready |
| 7–8 | Minor issues only |
| 5–6 | Moderate issues, needs work |
| 3–4 | Significant problems |
| 0–2 | Critical — do not merge |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Optional | Powers all AI features (mock used if absent) |
| `FEEDBACK_STORE` | Optional | Path for feedback JSON file (default: `feedback_store.json`) |
