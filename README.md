# Great Fit – Job Application Assistant

A full-stack web application that leverages Large Language Models (LLMs) to analyze your resume, evaluate job postings against your profile, and suggest tailored improvements, helping you quickly identify the **greatest fit** roles and streamline your application process.

---

## ✨ Key Features

| Area          | Capability                                                                                                                               |
| :------------ | :--------------------------------------------------------------------------------------------------------------------------------------- |
| **Resume**    | • Upload PDF/DOCX/TXT and extract structured profile using LLM <br>• View profile in collapsible UI sections                               |
| **Jobs**      | • Add jobs by pasting full description (LLM extracts title/company/details) <br>• View, select, delete saved jobs <br>• Automatic background ranking & tailoring upon adding a job |
| **Analysis**  | • Match scoring (0-10) with color scale <br>• Detailed LLM explanation for the score <br>• LLM-generated suggestions for tailoring your resume/profile |
| **Real-time** | • Server-Side Events (SSE) stream job processing status (ranking, tailoring) and updates processing indicators                           |
| **Auth**      | • Optional AWS Cognito integration for user accounts (toggleable via env var) <br>• Secure JWT-based authentication for API endpoints      |
| **Billing**   | • Optional Stripe integration for purchasing credits (toggleable via env var) <br>• Credit deduction per job processed                    |
| **UX**        | • Tailwind CSS styled responsive UI <br>• Alpine.js for dynamic elements & toast notifications <br>• HTMX for partial page updates (future potential) <br> • Drag & drop resume upload |
| **Observability** | • Structured JSON logging with request context <br>• AWS X-Ray tracing integration (optional) <br>• CloudWatch Embedded Metrics for background tasks |

---

## 🏗 Tech Stack

| Layer         | Tech                                                                                                                                                              |
| :------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Backend**   | **Python 3.11** · **FastAPI** · SQLAlchemy (ORM) · Alembic (Migrations) · Pydantic (Validation) · `structlog` (Logging)                                            |
| **LLM**       | [`openai`](https://github.com/openai/openai-python) client via **OpenRouter** API · [`instructor`](https://github.com/jxnl/instructor) for structured output (JSON) |
| **Database**  | PostgreSQL (Production via AWS RDS) · SQLite (Local Dev/Testing)                                                                                                  |
| **Real-time** | Server-Sent Events (SSE) via `sse-starlette`                                                                                                                      |
| **Frontend**  | **Tailwind CSS 4** (CLI build) · **Alpine.js** · **HTMX** · Jinja2 Templates · Vanilla JS Modules                                                                   |
| **Auth**      | **AWS Cognito** (Optional) · `python-jose` for JWT validation                                                                                                     |
| **Billing**   | **Stripe** (Optional)                                                                                                                                             |
| **Infra**     | **AWS CDK v2** (Python) · AWS App Runner · AWS RDS Aurora Serverless v2 · AWS ECR · AWS Secrets Manager · AWS VPC · CloudWatch · SNS                                |
| **Deployment**| **Docker** · **GitHub Actions** (CI/CD for build, push to ECR, CDK deploy)                                                                                          |
| **Tooling**   | Node.js / npm (for Tailwind) · `pytest` (Testing)                                                                                                                 |

---

## 📂 Project Structure (Key Areas)

```
.
├── .github/workflows/deploy.yml # GitHub Actions CI/CD pipeline
├── infra/                     # AWS CDK Infrastructure code (see infra/README.md)
│   ├── app.py                 # CDK App entrypoint
│   ├── infra_stack.py         # Main CDK Stack definition
│   └── requirements.txt       # CDK Python dependencies
├── static/
│   ├── css/                   # Compiled Tailwind CSS (generated, not committed)
│   ├── js/                    # Frontend JS modules (auth, core, jobs, profile, sse, ui, upload)
│   └── profileFormatter.js    # JS to render profile data
├── src/
│   └── index.css              # Tailwind input CSS file
├── templates/                 # Jinja2 HTML templates
│   ├── base.html              # Base template, loads CSS/JS
│   ├── index.html             # Main application page
│   └── billing_*.html         # Stripe success/cancel pages
├── alembic/                   # Alembic migration scripts
├── alembic.ini                # Alembic configuration
├── auth.py                    # Cognito JWT verification logic
├── crud.py                    # Database Create/Read/Update/Delete operations
├── database.py                # SQLAlchemy setup (engine, session, Base)
├── llm_interaction.py         # Functions calling OpenRouter/LLM APIs
├── logic.py                   # Core business logic (resume parsing, job ranking/tailoring)
├── main.py                    # FastAPI application entrypoint, defines API routes
├── models.py                  # SQLAlchemy ORM models (User, Job)
├── observability.py           # Logging, Tracing (X-Ray), Metrics setup
├── schemas.py                 # Pydantic models for API validation & LLM structured output
├── settings.py                # Application settings using Pydantic BaseSettings (reads .env)
├── dockerfile                 # Dockerfile for building the application image
├── docker-entrypoint.sh       # Script run at container start (runs migrations)
├── requirements.txt           # Backend Python dependencies
├── package.json               # Node.js dependencies (Tailwind) & scripts
├── tailwind.config.js         # Tailwind CSS configuration
├── .env.example               # Example environment variables
└── README.md                  # This file
```

---

## ⚡ Quick Start (Local Development)

### Prerequisites

*   Python 3.11+
*   Node.js 18+ and npm
*   An OpenRouter API Key (sign up at [openrouter.ai](https://openrouter.ai/))

### 1. Clone & Enter Repository

```bash
git clone https://github.com/your-username/great-fit.git # Replace with your repo URL
cd great-fit
```

### 2. Setup Python Environment & Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install Node Dependencies (for Tailwind CSS)

```bash
npm install
```

### 4. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit the `.env` file and **at minimum**, add your OpenRouter API key:

```env
OPENROUTER_API_KEY="sk-or-v1-..."
```

**Optional Configuration:**

*   **Authentication/Billing:** By default, `AUTH_BILLING_ENABLED` is `true`. For local development *without* needing Cognito or Stripe, set it to `false` in your `.env` file:
    ```env
    AUTH_BILLING_ENABLED=false
    ```
    If you want to test with Cognito/Stripe locally, you'll need to set the `COGNITO_*` and `STRIPE_*` variables accordingly.
*   **Database:** The default is a local SQLite file (`./great_fit.db`). You can configure a PostgreSQL database by setting `DATABASE_URL` or individual `DB_*` variables.

### 5. Run Database Migrations

The application uses Alembic for database migrations. The included `docker-entrypoint.sh` runs migrations automatically in the container. For local development, run them manually the first time (or whenever models change):

```bash
# Ensure your .env file is configured (DATABASE_URL or DB_* vars)
alembic upgrade head
```
*(Note: If using the default SQLite, this creates `great_fit.db` if it doesn't exist)*

### 6. Run the Application

You need two terminals:

**Terminal 1: Tailwind CSS Watcher**
(Compiles Tailwind CSS automatically when you change styles in templates/JS)

```bash
npm run dev
```

**Terminal 2: FastAPI Backend Server**
(Serves the API and frontend)

```bash
uvicorn main:app --reload --port 8000
```

### 7. Access the Application

Open your browser and navigate to <http://127.0.0.1:8000> 🎉

---

## 🚀 Production & Deployment

*   **Build CSS:** Before deploying, build the minified production CSS:
    ```bash
    npm run build
    ```
*   **Docker:** A `dockerfile` is provided to containerize the application. It includes building the production CSS and running migrations on startup.
*   **Infrastructure:** The `infra/` directory contains an AWS CDK stack to provision the necessary AWS resources (VPC, RDS, ECR, App Runner, Secrets Manager, etc.). See the `infra/README.md` for details.
*   **CI/CD:** The `.github/workflows/deploy.yml` pipeline automates:
    1.  Building the Docker image.
    2.  Pushing the image to AWS ECR.
    3.  Deploying the CDK infrastructure stack (which updates App Runner to use the new image).

---

## 🧪 Running Tests

The project uses `pytest` for testing.

```bash
# Ensure development dependencies are installed (pip install -r requirements.txt)
pytest
```

Tests run against a temporary SQLite database (`great-fit-test.db`) defined in `conftest.py`.

---

## 🤖 API Reference (High-Level)

| Method   | Path                         | Auth? | Description                                      |
| :------- | :--------------------------- | :---- | :----------------------------------------------- |
| `GET`    | `/`                          | Yes   | Serves the main HTML page (index.html)           |
| `GET`    | `/users/me`                  | Yes   | Get current authenticated user details & credits |
| `POST`   | `/resume/upload`             | Yes   | Upload resume file, parse, save profile        |
| `GET`    | `/profile/`                  | Yes   | Get current user's parsed profile data           |
| `GET`    | `/jobs/`                     | Yes   | List all saved jobs for the user                 |
| `POST`   | `/jobs/markdown`             | Yes   | Submit raw job markdown for processing (async)   |
| `GET`    | `/jobs/{job_id}`             | Yes   | Get details for a specific job                   |
| `DELETE` | `/jobs/{job_id}`             | Yes   | Delete a specific job                            |
| `GET`    | `/stream-jobs`               | Yes   | SSE stream for job processing updates            |
| `POST`   | `/billing/checkout-session`  | Yes   | Create a Stripe checkout session                 |
| `POST`   | `/billing/webhook`           | No    | Stripe webhook handler for payment events        |
| `GET`    | `/billing/success`           | No    | Stripe payment success page                      |
| `GET`    | `/billing/cancel`            | No    | Stripe payment cancelled page                    |

*(Authentication is enforced only if `AUTH_BILLING_ENABLED` is true)*

---

## 🔐 Authentication & Billing

*   Authentication uses AWS Cognito via the Hosted UI (Authorization Code Grant with PKCE).
*   Billing uses Stripe Checkout.
*   Both features can be **disabled** for local development or self-hosting without these services by setting `AUTH_BILLING_ENABLED=false` in the `.env` file.
*   When disabled, the backend uses a default local user (`local@example.com`) and does not require in-app credits.
*   When enabled, API routes require a valid Cognito JWT (`Authorization: Bearer <token>`), and job processing deducts credits.

---

## 📊 Observability

*   **Logging:** Uses `structlog` for structured JSON logging. Includes `request_id` context for tracing requests across logs and SSE events.
*   **Tracing:** Integrates with AWS X-Ray via `aws-xray-sdk` (optional, enabled via `ENABLE_XRAY=1` env var). Patches common libraries (requests, boto3, psycopg2/sqlite3).
*   **Metrics:** Uses `aws-embedded-metrics` to send custom metrics to CloudWatch (e.g., `jobs_submitted`, `jobs_completed`, `jobs_failed`) from background tasks.

---

## License

MIT © Noah Wiggin
