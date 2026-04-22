# Testing GitLab Webhooks Locally

If you use GitLab for your repositories and Merge Requests, you can also test the AI Code Review Agent by pointing GitLab webhooks straight to your local server!

## 1. Start your local server and ngrok

First, ensure your FastAPI application is running locally:
```bash
uvicorn app.main:app --reload
```

Next, use ngrok to expose your port 8000:
```bash
ngrok http 8000
```
Ngrok will give you a public Forwarding URL (e.g., `https://a1b2c3d4.ngrok.app`).

## 2. Configure the Webhook in GitLab

Because our backend dynamically evaluates the MR payload, **one webhook configuration works for entire GitLab Groups and Instances.**

### Option A: Single Repository Webhook
1. Go to your GitLab Project -> **Settings** -> **Webhooks**.

### Option B: GitLab Group Webhook (Review ALL Repos in Group)
1. Go to your GitLab Group -> **Settings** -> **Webhooks**.
2. This is extremely powerful because any MR opened in **any** project inside this group will trigger the review!

### Webhook Settings:
- **URL**: Enter your ngrok forwarding URL + `/webhook/gitlab` 
  *(e.g., `https://a1b2c3d4.ngrok.app/webhook/gitlab`)*
- **Secret token**: Leave blank for local testing.
- **Trigger**: Check **Merge request events**.
- Uncheck all other events.
- **Enable SSL verification**: Keep checked (ngrok provides valid HTTPS).
- Click **Add webhook**.

## 3. Test it!

Open a new Merge Request on GitLab. The agent will respond in your local terminal:
1. GitLab beams the MR payload to your ngrok URL.
2. The `/webhook/gitlab` endpoint reads the payload and extracts the `web_url` and MR ID.
3. The server downloads the `.diff` representation of the Merge Request.
4. OpenAI runs the analysis and logs the resulting score, bugs, and strengths!
