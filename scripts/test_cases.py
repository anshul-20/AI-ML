import requests
import json

def test_webhook_pr_opened():
    print("\n--- TEST CASE 1: Valid GitHub PR Opened ---")
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 1,
            "diff_url": "https://patch-diff.githubusercontent.com/raw/fastapi/fastapi/pull/11266.diff"
        },
        "repository": {
            "full_name": "fastapi/fastapi"
        }
    }
    
    headers = {"x-github-event": "pull_request", "Content-Type": "application/json"}
    try:
        response = requests.post("http://127.0.0.1:8001/webhook/github", json=payload, headers=headers)
        print("Status Code:", response.status_code)
        print("Response JSON:\n", json.dumps(response.json(), indent=2))
    except Exception as e:
        print("Error sending request:", e)

def test_webhook_unsupported_event():
    print("\n--- TEST CASE 2: Unsupported GitHub Event (Push without PR) ---")
    headers = {"x-github-event": "push", "Content-Type": "application/json"}
    try:
        response = requests.post("http://127.0.0.1:8001/webhook/github", json={"some": "data"}, headers=headers)
        print("Status Code:", response.status_code)
        print("Response:", response.json())
    except Exception as e:
        print("Error sending request:", e)

def test_direct_review():
    print("\n--- TEST CASE 3: Direct API /review Call (Git Hook Simulation) ---")
    diff_payload = "diff --git a/test.py b/test.py\n+++ b/test.py\n+password = 'super_secret123'"
    payload = {
        "repo": "local/test",
        "pr_id": 0,
        "diff": diff_payload
    }
    try:
        response = requests.post("http://127.0.0.1:8001/review", json=payload)
        print("Status Code:", response.status_code)
        print("Response JSON:\n", json.dumps(response.json(), indent=2))
    except Exception as e:
        print("Error sending request:", e)

def test_webhook_gitlab_mr():
    print("\n--- TEST CASE 4: Valid GitLab MR Opened ---")
    payload = {
        "object_kind": "merge_request",
        "event_type": "merge_request",
        "object_attributes": {
            "iid": 30000,
            "action": "open"
        },
        "project": {
            "path_with_namespace": "gitlab-org/gitlab",
            "web_url": "https://gitlab.com/gitlab-org/gitlab-foss"
        }
    }
    
    headers = {"x-gitlab-event": "Merge Request Hook", "Content-Type": "application/json"}
    try:
        response = requests.post("http://127.0.0.1:8001/webhook/gitlab", json=payload, headers=headers)
        print("Status Code:", response.status_code)
        print("Response JSON:\n", json.dumps(response.json(), indent=2))
    except Exception as e:
        print("Error sending request:", e)

if __name__ == "__main__":
    test_webhook_pr_opened()
    test_webhook_unsupported_event()
    test_direct_review()
    test_webhook_gitlab_mr()
    print("\nTests completed! You can stop the script now or kill background server.")
