"""MailDemo — demo app showing Mailpit SMTP config via uses: directive."""
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "1025")


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
def index():
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>MailDemo</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background:#0f172a; color:#e2e8f0;
           min-height:100vh; display:flex; flex-direction:column; align-items:center;
           justify-content:center; gap:1.5rem; padding:2rem; }}
    h1 {{ font-size:2rem; font-weight:700; }}
    h1 span {{ color:#34d399; }}
    .card {{ background:#1e293b; border:1px solid #334155; border-radius:.75rem;
             padding:1.5rem 2rem; max-width:480px; width:100%; }}
    .card h2 {{ font-size:.8rem; text-transform:uppercase; letter-spacing:.08em;
                color:#64748b; margin-bottom:.75rem; }}
    code {{ background:#0f172a; padding:.1em .4em; border-radius:4px; color:#34d399; font-size:.85em; }}
    a {{ color:#34d399; }}
  </style>
</head>
<body>
  <h1>Mail<span>Demo</span></h1>
  <div class="card">
    <h2>SMTP config (injected via uses: mailpit)</h2>
    <p>Host: <code>{SMTP_HOST}</code><br>Port: <code>{SMTP_PORT}</code></p>
  </div>
  <div class="card">
    <h2>Mailpit web UI</h2>
    <p><a href="https://mail.test" target="_blank">https://mail.test</a></p>
    <p style="color:#64748b;font-size:.85rem;margin-top:.5rem">
      All emails sent to <code>{SMTP_HOST}:{SMTP_PORT}</code> appear here.
    </p>
  </div>
</body>
</html>"""
