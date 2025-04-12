# Job Application Assistant

This project uses Language Models (LLMs) to help you improve your job applications. The current code is a **Proof-of-Concept (PoC)** with the following features:

*   Use your resume to automatically generate a profile.
*   Paste a raw job description, and the LLM will try to format it nicely.
*   Compare your saved jobs to your profile and rate them by how fit you are for the role (based on your resume).
*   Generate resume tailoring suggestions for saved jobs.

## Tech Stack (for the PoC)

*   **Backend:** Python / FastAPI
*   **Database:** SQLite (via SQLAlchemy)
*   **LLM:** OpenRouter API (using `openai` client lib + `instructor` for structured output)
*   **Frontend:** HTML, CSS, JavaScript
*   **Core Libs:** `uvicorn`, `python-dotenv`, `python-multipart`, `PyPDF2`, `python-docx`, `aiofiles`
*   **Testing:** `pytest`, `httpx`, `pytest-asyncio`, `pytest-env`

## Getting Started

1.  **Clone:**
    ```bash
    git clone https://github.com/wigginno/job-application-assistant.git
    cd job-application-assistant
    ```

2.  **Setup Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    ```

3.  **Install Deps:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure API Key:**
    *   Copy `.env.example` to `.env`: `cp .env.example .env`
    *   Edit `.env` and add your OpenRouter key:
        ```env
        # Get from OpenRouter account
        OPENROUTER_API_KEY="sk-or-v1-..."
        ```

## Running the PoC

1.  **Start Server:**
    ```bash
    # --reload restarts server on code changes
    uvicorn main:app --reload --port 8000
    ```

2.  **Open in Browser:**
    `http://127.0.0.1:8000`

## Running Tests

Make sure your virtual env is active and `.env` is configured.

```bash
pytest
```

## Project Layout

```
job-application-assistant/
├── main.py             # FastAPI app, routes, static files
├── logic.py            # Core application logic (LLM calls, processing, cache)
├── llm_interaction.py  # Functions for talking to the LLM API via Instructor
├── crud.py             # Database CRUD operations
├── models.py           # SQLAlchemy DB models
├── schemas.py          # Pydantic models (API validation, LLM structure)
├── database.py         # DB connection setup
├── static/             # Frontend Assets (HTML, CSS, JS)
│   ├── index.html
│   ├── script.js       # Main frontend logic
│   └── profileFormatter.js # Helper for profile display
├── requirements.txt    # Python dependencies
├── .env                # API keys etc. (**Do not commit!**)
├── test_main.py        # Integration tests for API endpoints
├── conftest.py         # Pytest setup/fixtures
└── job_assistant_poc.db # SQLite file (created automatically)
```

## PoC Scope & Next Steps

This PoC is intentionally limited:

*   **Single User:** Hardcoded for `user_id=1`. Real auth is needed for multi-user support.
*   **Minimal UI:** Frontend is just functional, not pretty.
*   **Basic Errors:** Error handling could be more robust.
*   **Prompts:** LLM prompts are basic and could be tuned for better results.
*   **Simple Cache:** Uses in-memory caching; a persistent cache (e.g., Redis) would be better.
*   **Autofill:** Very experimental, needs significant development.
*   **No Deployment Setup:** Configured for local development only.
