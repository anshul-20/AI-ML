# Testing GitHub Webhooks Locally

If you want the AI Code Review Agent to automatically review code when someone opens or updates a Pull Request on a real GitHub repository, you'll need to expose your local FastAPI application to the internet so GitHub can send HTTP POST payloads to it.

Here is the easiest way to test this on your local machine using [ngrok](https://ngrok.com/).

## 1. Start your local server

Make sure your agent is running locally on port 8000.

```bash
uvicorn app.main:app --reload
```

## 2. Expose the server using ngrok

Download and install ngrok, then run the following command to expose port 8000:

```bash
ngrok http 8000
```

Ngrok will give you a public Forwarding URL that looks something like this:
`https://a1b2c3d4.ngrok.app`

## 3. Configure the Webhook in GitHub

You can configure webhooks for a **single repository** or for an entire **GitHub Organization**! Because our backend dynamically extracts the repository name from every payload, **the same webhook URL works effortlessly for 100+ repos**.

### Option A: Single Repository Webhook
1. Go to your GitHub repository -> **Settings** -> **Webhooks** -> **Add webhook**.

### Option B: Organization-Level Webhook (Review ALL Repos)
1. Go to your GitHub Organization page -> **Settings** -> **Webhooks** -> **Add webhook**.
2. This will capture Pull Requests for **every** repository inside your organization automatically.

### Webhook Settings:
- **Payload URL**: Enter your ngrok forwarding URL + `/webhook/github` 
  *(e.g., `https://a1b2c3d4.ngrok.app/webhook/github`)*
- **Content type**: Select `application/json`.
- **Which events would you like to trigger this webhook?**: 
  - Select **Let me select individual events.**
  - Uncheck "Pushes" if you only want PRs.
  - Check **Pull requests**.
- Click **Add webhook**.

## 4. Test it!

Now, open a Pull Request (or push a commit to an existing Pull Request) on your GitHub repository.
1. GitHub will send a JSON payload to your ngrok URL.
2. Ngrok will forward it to your local FastAPI server.
3. The `/webhook/github` endpoint will detect the `diff_url`.
4. The server downloads the diff and runs the OpenAI review.
5. You will see the results logged in your local terminal window!

*(Note: If you want the agent to automatically post the review as a comment on the GitHub PR, you will need to extend the webhook handler in `app/main.py` using a `GITHUB_TOKEN` and the GitHub Issues API. Right now, it processes the review locally and logs the output.)*
