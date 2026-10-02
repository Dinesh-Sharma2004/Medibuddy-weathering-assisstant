# Deploying to Streamlit Community Cloud

This app is a **Streamlit** server (a long-running Python process with WebSockets).
It cannot run on static/serverless hosts like Netlify, GitHub Pages or Vercel — it needs a
Python app host. Streamlit Community Cloud is free and purpose-built for it, and deploys
straight from this GitHub repo.

## Why not Netlify?
Netlify serves static files and short-lived JS/Go serverless functions. Streamlit holds an
open server process and a WebSocket to each browser, which Netlify has no way to run — the
page would load blank or error. Use one of the Python hosts below instead.

## One-time setup (≈3 minutes)

1. **Push this repo to GitHub** (branch `main`). The remote is already set:
   `git push -u origin main` (authenticate with a Personal Access Token).
2. Go to **https://share.streamlit.io** and sign in with GitHub; authorize access to the repo.
3. Click **Create app → Deploy a public app from GitHub** and fill in:
   - **Repository:** `Dinesh-Sharma2004/Medibuddy-weathering-assisstant`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **Advanced settings → Python version:** `3.12`
4. Open **Advanced settings → Secrets** (or, after first deploy, **Manage app → Settings →
   Secrets**) and paste your real values in TOML form (see `.streamlit/secrets.toml.example`):
   ```toml
   OPENAI_API_KEY = "sk-or-gsk-..."     # your real key
   OPENAI_MODEL = "openai/gpt-oss-20b"  # or whatever model your endpoint serves
   OPENAI_BASE_URL = "https://api.groq.com/openai/v1"
   ```
   Streamlit exposes these as environment variables, which is exactly what the app reads
   (`os.environ` via `python-dotenv`) — no code change needed.
5. Click **Deploy**. First build installs `requirements.txt` (pinned) and starts the app.

## After deploy
- The app URL looks like `https://<your-app-name>.streamlit.app`.
- Change a policy by editing `sops/sops.yaml` and pushing — the app reloads the file on each
  request, so no redeploy of code is needed for policy changes (the loader re-reads per turn;
  Streamlit redeploys the repo on push).
- Logs and reboot are under **Manage app** in the Streamlit dashboard.

## What is committed vs secret
- **Committed:** `app.py`, `src/`, `sops/`, `requirements.txt`, `.streamlit/config.toml`,
  `.streamlit/secrets.toml.example`.
- **Never committed (gitignored):** `.env`, `.streamlit/secrets.toml`. Put the real key only in
  the Streamlit **Secrets** box, never in the repo.

## Other Python hosts (if you prefer)
The same app runs on any host that can run a Python process:
- **Hugging Face Spaces** (Streamlit SDK) — free; set the key as a Space secret.
- **Render / Railway / Fly.io** — run `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`;
  set the key as an env var. (Ask and I'll add a Dockerfile/Procfile.)
