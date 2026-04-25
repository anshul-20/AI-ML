"""
Feature 4: Automated Documentation Generator
Generates changelog, API change notes, and developer notes from a Git diff.
"""

import logging
import re
from typing import List

from app.logger import log_event
from app.openai_client import call_openai, parse_json_response
from app.prompt import MAX_DIFF_CHARS
from app.schemas import DocsRequest, DocsResponse

logger = logging.getLogger(__name__)

_DOCS_SYSTEM = (
    "You are a technical documentation generator. "
    "Analyze Git diffs and produce concise, accurate developer documentation. "
    "Return ONLY valid JSON. Never hallucinate changes not in the diff."
)

_DOCS_PROMPT = """You are a technical documentation generator.

Analyze the following Git diff carefully.

Your job:
1. Write a concise summary of what changed and why it matters.
2. Create changelog entries (imperative mood, e.g. "Add user auth endpoint").
3. List any API-level changes (new routes, changed signatures, removed endpoints).
4. Write developer notes (migration steps, breaking changes, config changes).

STRICT RULES:
- Only document changes actually present in the diff
- Do NOT hallucinate features or APIs not in the diff
- Keep entries concise (1 sentence each)
- Use imperative mood for changelog

Git diff:
{diff}

Return ONLY this JSON:
{{
  "summary": "2-3 sentence overview of what changed",
  "changelog": [
    "Action taken (file or component)"
  ],
  "api_changes": [
    "Describe API-level change, or empty array if none"
  ],
  "developer_notes": [
    "Migration step, breaking change, or config note"
  ]
}}"""


# ── Mock documentation ────────────────────────────────────────────────────────

def _mock_docs(diff: str) -> dict:
    """Generate basic docs from diff heuristics when no API key is set."""
    added_files: List[str] = []
    modified_files: List[str] = []
    has_route = False

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" b/")
            fname = parts[-1] if len(parts) > 1 else "unknown"
            if "new file" in diff[diff.find(line):diff.find(line) + 100]:
                added_files.append(fname)
            else:
                modified_files.append(fname)
        if any(kw in line for kw in ("@app.get", "@app.post", "@router.", "def get_", "def post_",
                                      "app.route", "router.get", "router.post")):
            has_route = True

    changelog = []
    for f in added_files[:3]:
        changelog.append(f"Add {f}")
    for f in modified_files[:3]:
        changelog.append(f"Update {f}")
    if not changelog:
        changelog = ["Update source files based on diff"]

    api_changes = ["New route or handler detected — review OpenAPI spec"] if has_route else []

    all_files = added_files + modified_files
    notes = [f"Review changes in: {', '.join(all_files[:4])}"] if all_files else []

    return {
        "summary": (
            "Mock documentation: changes detected via diff heuristics. "
            "Set OPENAI_API_KEY for AI-generated docs."
        ),
        "changelog": changelog,
        "api_changes": api_changes,
        "developer_notes": notes,
    }


async def generate_docs(req: DocsRequest) -> DocsResponse:
    """
    Generate documentation from a Git diff using OpenAI.
    Falls back to heuristic mock when no API key is configured.
    """
    if not req.diff.strip():
        return DocsResponse(
            summary="No diff provided.",
            changelog=[],
            api_changes=[],
            developer_notes=[],
        )

    log_event(logger, "docs_generate", diff_length=len(req.diff))

    diff_truncated = req.diff[:MAX_DIFF_CHARS]
    prompt = _DOCS_PROMPT.format(diff=diff_truncated)

    raw = await call_openai(prompt, system=_DOCS_SYSTEM, max_tokens=1024)

    if raw:
        try:
            data = parse_json_response(raw)
            log_event(logger, "docs_generated",
                      changelog_items=len(data.get("changelog", [])),
                      api_items=len(data.get("api_changes", [])))
            return DocsResponse(
                summary=data.get("summary", ""),
                changelog=data.get("changelog", []),
                api_changes=data.get("api_changes", []),
                developer_notes=data.get("developer_notes", []),
            )
        except Exception as exc:
            logger.warning("Docs parsing failed, using mock: %s", exc)

    data = _mock_docs(req.diff)
    return DocsResponse(**data)
