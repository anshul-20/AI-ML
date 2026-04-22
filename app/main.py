import logging
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.schemas import ReviewRequest, ReviewResponse
from app.reviewer import perform_review
from app.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Code Review Agent",
    description="LLM-powered code review service for CI/CD pipelines",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/review", response_model=ReviewResponse)
async def review_pr(request: ReviewRequest):
    logger.info(
        "Incoming review request | repo=%s pr_id=%s diff_length=%d",
        request.repo,
        request.pr_id,
        len(request.diff),
    )

    if not request.diff.strip():
        logger.warning("Empty diff received for repo=%s pr_id=%s", request.repo, request.pr_id)
        raise HTTPException(status_code=400, detail="Diff cannot be empty.")

    result = await perform_review(request.diff)
    logger.info("Review completed | repo=%s pr_id=%s score=%.1f issues=%d",
                request.repo, request.pr_id, result.score, len(result.issues))
    return result


@app.post("/webhook/github")
async def github_webhook(request: Request):
    """
    Handle GitHub webhook payloads for testing locally.
    Expects 'pull_request' events.
    """
    event = request.headers.get("x-github-event", "ping")
    if event == "ping":
        return {"status": "pong"}

    if event != "pull_request":
        return {"status": "ignored", "reason": f"Event {event} not handled"}

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = body.get("action")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"Action {action} on PR ignored"}

    pr = body.get("pull_request")
    if not pr:
        raise HTTPException(status_code=400, detail="Missing pull_request data")

    repo = body.get("repository", {}).get("full_name", "unknown")
    pr_id = pr.get("number")
    diff_url = pr.get("diff_url")

    if not diff_url:
        raise HTTPException(status_code=400, detail="Missing diff_url")

    logger.info("Received GitHub PR Webhook | repo=%s pr_id=%s action=%s", repo, pr_id, action)

    # Fetch the diff
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(diff_url, follow_redirects=True)
            resp.raise_for_status()
            diff_text = resp.text
        except Exception as e:
            logger.error("Failed to fetch diff from %s: %s", diff_url, e)
            raise HTTPException(status_code=500, detail="Could not retrieve diff")

    if not diff_text.strip():
        logger.warning("Empty diff at %s", diff_url)
        return {"status": "ignored", "reason": "Empty diff"}

    logger.info("Starting review for webhook diff (length=%d)", len(diff_text))
    result = await perform_review(diff_text)
    
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        sha = pr.get("head", {}).get("sha", "")
        
        # Build comment Markdown
        md = f"## AI Code Review (`{result.score}/10.0`)\n\n{result.summary}\n\n"
        if result.issues:
            md += "### Issues Found\n"
            for issue in result.issues:
                md += f"- **[{issue.severity.upper()}]** `{issue.file}`: **{issue.title}**\n"
                md += f"  - _{issue.description}_\n"
                md += f"  - **Fix:** {issue.suggestion}\n"
        if result.strengths:
            md += "\n### Strengths\n"
            for st in result.strengths:
                md += f"- {st}\n"

        gh_headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        async with httpx.AsyncClient() as client:
            # 1. Post Comment
            comments_url = f"https://api.github.com/repos/{repo}/issues/{pr_id}/comments"
            try:
                await client.post(comments_url, json={"body": md}, headers=gh_headers)
                logger.info("Posted Review Comment to PR #%s", pr_id)
            except Exception as e:
                logger.error("Failed to post comment to GitHub: %s", e)
                
            # 2. Post Status Check
            if sha:
                status_url = f"https://api.github.com/repos/{repo}/statuses/{sha}"
                state = "success" if result.score >= 5.0 else "failure"
                status_payload = {
                    "state": state,
                    "description": f"AI Code Review Score: {result.score}/10.0",
                    "context": "ai-code-review-agent"
                }
                try:
                    await client.post(status_url, json=status_payload, headers=gh_headers)
                    logger.info("Posted Status '%s' for commit %s", state, sha)
                except Exception as e:
                    logger.error("Failed to post status check: %s", e)

    logger.info("Webhook review completed | score=%.1f issues=%d", result.score, len(result.issues))
    return {"status": "reviewed", "review": result}


@app.post("/webhook/gitlab")
async def gitlab_webhook(request: Request):
    """
    Handle GitLab webhook payloads for testing locally.
    Expects 'Merge Request Hook' events.
    """
    event = request.headers.get("x-gitlab-event", "ping")
    if event == "ping":
        return {"status": "pong"}

    if event != "Merge Request Hook":
        return {"status": "ignored", "reason": f"Event {event} not handled"}

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    obj_attrs = body.get("object_attributes", {})
    action = obj_attrs.get("action")
    
    # Gitlab uses "open", "update", "reopen"
    if action not in ("open", "update", "reopen"):
        return {"status": "ignored", "reason": f"Action {action} on MR ignored"}

    project = body.get("project", {})
    repo = project.get("path_with_namespace", "unknown")
    mr_iid = obj_attrs.get("iid")
    web_url = project.get("web_url")

    if not mr_iid or not web_url:
        raise HTTPException(status_code=400, detail="Missing MR iid or project web_url")

    logger.info("Received GitLab MR Webhook | repo=%s mr_iid=%s action=%s", repo, mr_iid, action)

    # GitLab natively supports appending .diff to the MR URL to fetch the raw diff
    diff_url = f"{web_url}/-/merge_requests/{mr_iid}.diff"

    # Fetch the diff
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(diff_url, follow_redirects=True)
            resp.raise_for_status()
            diff_text = resp.text
        except Exception as e:
            logger.error("Failed to fetch diff from %s: %s", diff_url, e)
            raise HTTPException(status_code=500, detail="Could not retrieve diff. (Note: Private GitLab repos require an Access Token)")

    if not diff_text.strip():
        logger.warning("Empty diff at %s", diff_url)
        return {"status": "ignored", "reason": "Empty diff"}

    logger.info("Starting review for GitLab webhook diff (length=%d)", len(diff_text))
    result = await perform_review(diff_text)
    
    logger.info("GitLab Webhook review completed | score=%.1f issues=%d", result.score, len(result.issues))
    return {"status": "reviewed", "review": result}
