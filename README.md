# Great Fit
LLM-powered app that scores how well your resume stacks up for jobs you want to apply to, and provides concrete suggestions to tailor your resume for specific roles.

A running instance is at **https://greatfit.app**.

---

## Features
* **Resume-based profile generation** – upload PDF; LLM turns it into a structured profile
* **Evaluate how good of a fit you are on paper** – after you upload a resume, copy-paste raw job descriptions (e.g. from linkedin/indeed) into the interface and see how good of a fit you are for specific jobs
* **Match score (0‑10) w/ explanations** – weighted rubric (skills 40 % · experience 30 % · education 15 % · soft skills 15 %)
* **Tailoring suggestions** – 3‑5 concrete edits to make your resume fit better

---

## Demo

https://github.com/user-attachments/assets/e503475b-6303-4ab0-b3ed-64473afce8a0

## Quick Start (local)

```bash
git clone https://github.com/wigginno/great-fit.git
cd great-fit

# Python deps
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Front‑end assets (Tailwind)
npm install
npm run dev            # rebuild CSS on change (leave running)

# Environment
cp .env.example .env   # set OPENROUTER_API_KEY=sk‑or‑...

# Database (SQLite by default)
alembic upgrade head

# Run
uvicorn main:app --reload --port 8000
````

Browse to [http://localhost:8000](http://localhost:8000).

---

## Docker

```bash
docker build -t great-fit .
docker run --env-file .env -p 8080:8080 great-fit
```

---

## Directory Map

```
infra/          AWS CDK stack (App Runner, RDS, Secrets Mgr) - not used when self hosting
templates/      Jinja2 HTML (Tailwind + Alpine)
static/         JS modules (auth, jobs, sse, ui, …) & compiled CSS
main.py         FastAPI app & routes
logic.py        Async GPT calls (ranking, tailoring, parsing)
llm_interaction.py   OpenRouter client + prompt builders
models.py       SQLAlchemy ORM
schemas.py      Pydantic models (strict JSON output)
observability.py Structlog, CloudWatch EMF, X‑Ray - not used when self hosting
dockerfile      Multi‑stage build (Tailwind → slim Python)
```

---

## Testing

```bash
pytest
```

Runs against an ephemeral SQLite DB defined in `conftest.py`.

---

## API

| Method | Path           | Purpose                     |
| ------ | -------------- | --------------------------- |
| POST   | /resume/upload | Parse resume & save profile |
| GET    | /profile/      | Get current profile         |
| POST   | /jobs/markdown | Submit raw job post         |
| GET    | /jobs/         | List saved jobs             |
| GET    | /stream-jobs   | SSE feed (score / progress) |

---

## Production Notes

* Build minified CSS: `npm run build`.
* Image runs as `uvicorn main:app` on **port 8080**.
* CDK stack (`infra/`) provisions VPC, Aurora Serverless v2, secrets, App Runner and ties in Cognito + Stripe keys. Nothing here is required for self-hosting.

---

## License

MIT © 2025 Great Fit ( Noah Wiggin )
