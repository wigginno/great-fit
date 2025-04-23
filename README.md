# Great Fit – Job Application Assistant

A full-stack web app that leverages LLMs to analyse your resume, evaluate job postings and suggest tailored improvements, helping you quickly identify the **greatest fit** roles.

---

## ✨ Key Features

| Area | Capability |
|------|------------|
| Resume | • Upload PDF/DOC/TXT and extract structured profile <br>• View profile in collapsible UI sections |
| Jobs | • Add jobs via modal, live validation <br>• View, select, delete jobs <br>• Server-Side Events (SSE) stream real-time ranking/tailoring results |
| Analysis | • Match scoring (0-10) + colour scale <br>• Detailed LLM explanation <br>• Tailoring suggestions persisted to **localStorage** so they survive refreshes |
| UX | • Tailwind-styled responsive UI <br>• Alpine-powered toast notifications <br>• Keyboard-friendly modal workflow |

---

## 🏗 Tech Stack

| Layer | Tech |
|-------|------|
| Backend | **Python 3.11** · **FastAPI** · SQLModel/SQLAlchemy · SQLite |
| LLM | [`openai`](https://github.com/openai/openai-python) client via **OpenRouter** API + [`instructor`](https://github.com/jxnl/instructor) for structured output |
| Realtime | SSE endpoint (`/sse/{user_id}`) |
| Frontend | **Tailwind CSS 4** (CLI build) · **Alpine.js** · **HTMX** |
| Tooling | Node, npm scripts (`npm run dev / build`) |
| Tests | `pytest` |

---

## 📂 Project Structure (trimmed)

```
.
├── main.py                  # FastAPI entry-point
├── logic.py                 # Core resume / job processing
├── crud.py                  # DB operations
├── templates/               # Jinja2 templates (served by FastAPI)
│   └── base.html            # Loads Tailwind CSS + JS bundles
├── static/
│   ├── css/                 # Compiled Tailwind CSS
│   ├── js/                  # Front-end modules (events.js, jobs.js, …)
│   └── profileFormatter.js  # Renders profile collapsibles
├── src/
│   ├── index.css            # Tailwind input file (includes @tailwind directives)
│   └── tailwind.css         # (optionally) more granular layers
├── tailwind.config.js       # Purge paths & theme extension
├── package.json             # Tailwind CLI + scripts
└── requirements.txt         # Python deps
```

---

## ⚡ Quick Start (Local Dev)

### 1. Clone & enter repo
```bash
git clone https://github.com/wigginno/great-fit.git
cd great-fit
```

### 2. Python env & deps
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Node (Tailwind) deps
```bash
# Requires Node ≥ 18
npm install
```

### 4. Environment variables
Copy and edit `.env` (see `.env.example`) – at minimum set the LLM key:
```env
OPENROUTER_API_KEY="sk-or-…"
```

### 5. Run everything
Terminal #1 – Tailwind in watch mode (re-builds on class changes):
```bash
npm run dev
```
Terminal #2 – FastAPI backend:
```bash
uvicorn main:app --reload --port 8000
```
Head to <http://127.0.0.1:8000> 🎉

---

## 🏁 Production Build

1. Build minified CSS:
   ```bash
   npm run build
   ```
2. Ensure `.env` contains prod keys.
3. Launch with a real ASGI server (e.g. `gunicorn -k uvicorn.workers.UvicornWorker main:app`).

---

## 🧪 Running Tests
```bash
pytest
```

---

## 🤖 API Reference (high-level)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/users/{id}/resume/upload` | Upload resume file |
| GET  | `/users/{id}/profile/` | Get parsed profile |
| GET  | `/users/{id}/jobs/` | List jobs |
| POST | `/users/{id}/jobs/` | Save new job |
| GET  | `/users/{id}/jobs/{job_id}` | Get job details |
| DELETE | same | Remove job |
| GET  | `/sse/{id}` | SSE stream for ranking / tailoring events |

_(see `main.py` for full router)_

---

## 🔄 CSS Build Flow Explained

1. Edit Tailwind classes in templates or `static/js/**/*.js`.
2. Run `npm run dev` → Tailwind CLI watches `src/index.css` and template paths from `tailwind.config.js` and outputs compiled CSS to `static/css/tailwind.css`.
3. The compiled file is **NOT committed** – it’s generated per-build.

---

## 📋 TODO / Roadmap

- Authentication & multi-user support
- Better error handling & optimistic UI
- Deeper HTMX integration / partial updates
- Dockerfile for easy deployment
- CI pipeline (pytest + frontend lint/build)

---

## License

MIT © Noah Wiggin
