"""
conftest.py — shared pytest fixtures for the AI-Augmented CI/CD test suite.

Provides an authenticated TestClient that automatically includes the
X-API-Token header so the token_auth_middleware is satisfied in tests
regardless of whether AI_REVIEW_SECRET is set in .env.
"""

import os
import pytest
from fastapi.testclient import TestClient

# Load .env so AI_REVIEW_SECRET is available before the app is imported
from dotenv import load_dotenv
load_dotenv()

from app.main import app  # noqa: E402  (import after env load)


@pytest.fixture(scope="session")
def auth_headers() -> dict:
    """Return headers that satisfy the token_auth_middleware."""
    secret = os.getenv("AI_REVIEW_SECRET", "")
    return {"X-API-Token": secret} if secret else {}


@pytest.fixture(scope="session")
def client(auth_headers) -> TestClient:
    """
    Authenticated TestClient — automatically sends X-API-Token on every
    request so tests are not blocked by the auth middleware.
    """
    with TestClient(app, headers=auth_headers) as c:
        yield c
