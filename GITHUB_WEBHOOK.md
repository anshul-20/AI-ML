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

## 4. Enable Active PR Blocking (Optional but Recommended)

By default, the AI only logs reviews to your terminal. To allow the AI to actively comment on GitHub PRs and block bad code:

1. **Generate a GitHub Token**:
   - Go to your GitHub **Settings** -> **Developer settings** -> **Personal access tokens** -> **Tokens (classic)**.
   - Click **Generate new token**. Give it a descriptive name (e.g. `AI Code Reviewer Bot`).
   - Give it the **`repo`** scope (Full control of private repositories).
   - Copy the token and paste it into your local `.env` file as `GITHUB_TOKEN=ghp_...`.

2. **Enable Branch Protection**:
   - Go to your GitHub repository -> **Settings** -> **Branches**.
   - Add a branch protection rule for `main`.
   - Check **Require status checks to pass before merging**.
   - In the search box, search for and select **`ai-code-review-agent`** (This will only appear *after* the webhook has run at least once successfully).
   - Click **Save changes**.

## 5. Test it!

Now, open a Pull Request (or push a commit to an existing Pull Request) on your GitHub repository.
1. GitHub will send a JSON payload to your ngrok URL.
2. The `/webhook/github` endpoint will detect the Pull Request and run the OpenAI review.
3. Your local server will instantly post a **Markdown Comment** on the PR detailing exactly what's wrong with the code.
4. If the code scores below **5.0**, a **Red \u274c** will appear on the PR status, and GitHub will physically block the "Merge" button!
