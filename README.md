# AI Code Review Agent

A production-ready FastAPI service that performs automated AI-powered code reviews on Git diffs. Designed to plug into CI/CD pipelines as Feature 1 of an AI-augmented developer workflow.

---

## Features

- `POST /review` — Analyze a Git diff and return a structured JSON code review
- LLM-powered analysis via **Anthropic Claude** (with mock fallback for local dev)
- Detects: bugs, security issues (SQL injection, hardcoded secrets), performance problems, style issues, best-practice violations
- Retry logic, graceful JSON parsing, structured logging
- Fully testable without an API key

---

## Project Structure

```
ai-code-review-agent/
├── app/
│   ├── main.py       # FastAPI app & /review endpoint
│   ├── reviewer.py   # LLM orchestration, mock fallback, retry logic
│   ├── prompt.py     # Prompt template & diff truncation
│   ├── schemas.py    # Pydantic request/response models
│   └── utils.py      # Logging setup, JSON parsing helpers
├── tests/
│   └── test_review.py
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Quick Start

### 1. Install dependencies

```bash
cd ai-code-review-agent
pip install -r requirements.txt
```

### 2. (Optional) Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

If not set, the service uses a smart mock that detects common patterns (SQL injection, hardcoded secrets, missing type hints).

### 3. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

---

## Usage

### Basic curl

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "my-service",
    "pr_id": 42,
    "diff": "diff --git a/app.py b/app.py\n+++ b/app.py\n+def get_user(id):\n+    return db.query(\"SELECT * FROM users WHERE id=\" + id)"
  }'
```

### Expected response

```json
{
  "summary": "Critical SQL injection vulnerability detected...",
  "score": 2.0,
  "issues": [
    {
      "type": "security",
      "severity": "critical",
      "file": "app.py",
      "line": null,
      "title": "SQL Injection Vulnerability",
      "description": "String concatenation is used to build a SQL query...",
      "suggestion": "Use parameterized queries: db.query('SELECT * FROM users WHERE id = %s', (id,))"
    }
  ],
  "strengths": []
}
```

---

## Running Tests

```bash
pytest tests/ -v
```

All tests run without an API key using the built-in mock LLM.

---

## Docker

```bash
docker build -t ai-code-review-agent .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... ai-code-review-agent
```

---

## API Reference

### `POST /review`

| Field | Type | Description |
|-------|------|-------------|
| `repo` | string | Repository name |
| `pr_id` | integer | Pull request ID |
| `diff` | string | Raw git diff output |

#### Response

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | 2–3 line overall assessment |
| `score` | float (0–10) | Code quality score |
| `issues` | array | List of detected issues |
| `strengths` | array | Observed good practices |

#### Issue object

| Field | Type | Values |
|-------|------|--------|
| `type` | string | `bug`, `security`, `performance`, `style`, `best_practice` |
| `severity` | string | `low`, `medium`, `high`, `critical` |
| `file` | string | Filename |
| `line` | int or null | Line number if known |
| `title` | string | Short issue label |
| `description` | string | Full explanation |
| `suggestion` | string | Concrete fix |

---

## Score Guide

| Score | Meaning |
|-------|---------|
| 9–10 | Production-ready |
| 7–8 | Minor issues |
| 5–6 | Moderate issues |
| 3–4 | Significant problems |
| 0–2 | Critical issues, do not merge |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | _(none)_ | Enables real Claude reviews |
