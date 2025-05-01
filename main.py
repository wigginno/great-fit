import traceback, sys
import asyncio
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Request,
    Header,
)
from fastapi import Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
import json
from pydantic import BaseModel
import os
import tempfile
from fastapi import status
import fitz
from docx import Document
import logging
from observability import init_observability
import asyncio
from sse_starlette.sse import EventSourceResponse
import openai
import stripe
import structlog
from structlog.contextvars import get_contextvars

import models
import schemas
import crud
import logic
from database import SessionLocal, create_db_and_tables, get_db
from auth import get_current_user
from settings import get_settings, Settings
from request_id_middleware import RequestIdMiddleware

# Initialise observability before creating app
init_observability()
logger = structlog.get_logger(__name__)

logging.warning(f"AUTH_BILLING_ENABLED setting is: {get_settings().auth_billing_enabled}")

# Create DB tables on startup
create_db_and_tables()

app = FastAPI(
    title="Great Fit",
    description="Backend API for Great Fit job application assistant",
    version="0.1.0",
)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Semaphore to limit concurrent database writes for SQLite
db_write_semaphore = asyncio.Semaphore(1)

# --- CORS Middleware --- Set up CORS
# Allow all origins for PoC purposes
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIdMiddleware)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates directory
templates = Jinja2Templates(directory="templates")


# --- SSE Connection Manager (Simple In-Memory) --- #
class ConnectionManager:
    def __init__(self):
        # Dictionary to hold asyncio Queues for each user_id
        self.active_connections: dict[int, asyncio.Queue] = {}
        self.processing_counts: dict[int, int] = {}

    async def connect(self, user_id: int) -> asyncio.Queue:
        """Registers a new user connection and returns their queue."""
        queue = asyncio.Queue()
        self.active_connections[user_id] = queue
        logger.info("SSE connection established", user_id=user_id)
        return queue

    def disconnect(self, user_id: int):
        """Removes a user's queue when they disconnect."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info("SSE connection closed", user_id=user_id)

    async def send_personal_message(
        self, message: str | dict, user_id: int, event: str = "message"
    ) -> None:
        if user_id in self.active_connections:
            # If the message is a dict, inject request_id for correlation if missing
            if isinstance(message, dict):
                if "request_id" not in message:
                    req_id = get_contextvars().get("request_id")
                    if req_id:
                        message["request_id"] = req_id
                json_data = json.dumps(message)
            else:
                json_data = message
            await self.active_connections[user_id].put(
                {"event": event, "data": json_data}
            )
            logger.info("Sent SSE event", sse_event=event, user_id=user_id)
        else:
            logger.warning("Attempted to send SSE to disconnected user", user_id=user_id)

    async def increment_processing_count(self, user_id: int):
        if user_id in self.active_connections:
            self.processing_counts[user_id] = self.processing_counts.get(user_id, 0) + 1
            count = self.processing_counts[user_id]
            await self.active_connections[user_id].put(
                {
                    "event": "processing_count_update",
                    "data": json.dumps({"count": count}),
                }
            )
            logger.info("Incremented processing count", user_id=user_id, count=count)

    async def decrement_processing_count(self, user_id: int):
        if (
            user_id in self.active_connections
            and self.processing_counts.get(user_id, 0) > 0
        ):
            self.processing_counts[user_id] -= 1
            count = self.processing_counts[user_id]
            await self.active_connections[user_id].put(
                {
                    "event": "processing_count_update",
                    "data": json.dumps({"count": count}),
                }
            )
            logger.info("Decremented processing count", user_id=user_id, count=count)
        elif user_id in self.processing_counts and self.processing_counts[user_id] <= 0:
            logger.info("Processing count is already 0", user_id=user_id)


manager = ConnectionManager()


# --- Root Endpoint --- Serve index page with Jinja2 Template --- #
@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    settings: Settings = Depends(get_settings),
    current_user: models.User = Depends(get_current_user) # <-- ADD THIS DEPENDENCY
):
    """Render the main index page.

    Uses Jinja2 template rendering instead of serving a static file so that we
    can progressively migrate to server-side rendering with HTMX and Alpine.js
    in the frontend.
    """
    # Get settings via dependency injection
    # settings = get_settings()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "env": "dev", # TODO: Make this dynamic based on actual environment?
            "auth_billing_enabled": settings.auth_billing_enabled,
            # Pass Cognito settings from the Settings object
            "cognito_user_pool_id": settings.cognito_user_pool_id or "",
            "cognito_app_client_id": settings.cognito_app_client_id or "",
            "cognito_domain": settings.cognito_domain or "",
            "aws_region": settings.aws_region or "",
        },
    )


# Add route for favicon.ico
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- User Endpoints ---
@app.post("/users/", response_model=schemas.User, tags=["Users"])
def create_user_endpoint(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)


# --- Authenticated current user endpoint ---
@app.get("/users/me", response_model=schemas.User, tags=["Auth"])
def get_me(current_user: models.User = Depends(get_current_user)):
    """Returns the authenticated user's database record."""
    return current_user


# --- Helper Functions for Resume Processing ---
async def extract_text_from_resume(file: UploadFile) -> str:
    """Extract text from various resume formats (PDF, DOCX, TXT)"""
    content_type = file.content_type
    file_content = await file.read()
    extracted_text = ""

    try:
        if content_type == "application/pdf":
            # Extract text from PDF using PyMuPDF (fitz)
            with fitz.open(stream=file_content, filetype="pdf") as doc:
                for page in doc:
                    extracted_text += page.get_text() + "\n"

        elif content_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ]:
            # Extract text from DOCX
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name

            try:
                doc = Document(temp_file_path)
                extracted_text = "\n".join([para.text for para in doc.paragraphs])
            finally:
                # Clean up the temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        elif content_type == "text/plain":
            # Already a text file
            extracted_text = file_content.decode("utf-8")

        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported file type: {content_type}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error extracting text from resume: {str(e)}"
        )

    return extracted_text


# --- User Profile Endpoints (Assuming user_id=1 for PoC) ---
@app.post("/profile/", response_model=schemas.UserProfile, tags=["User Profile"])
def create_or_update_profile_endpoint(
    profile: schemas.UserProfileCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        user = crud.create_user(db=db, user=schemas.UserCreate(email=current_user.email, cognito_sub=current_user.email))
    crud.create_or_update_user_profile(db=db, user_id=user_id, profile=profile)
    profile_json_str = crud.get_user_profile(db=db, user_id=user_id)
    if profile_json_str is None:
        return Response(
            status_code=204,
            headers={"X-Profile-Status": "no_profile_found"},
        )
    profile_data = json.loads(profile_json_str)
    return schemas.UserProfile(
        id=user_id, owner_email=user.email, profile_data=profile_data
    )


@app.post("/resume/upload", tags=["User Profile"])
async def upload_resume_endpoint(
    resume: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    resume_text = await extract_text_from_resume(resume)
    if not resume_text.strip():
        raise HTTPException(
            status_code=400, detail="Could not extract text from the resume"
        )
    profile_data = await logic.parse_resume_with_llm(resume_text)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        user = crud.create_user(db=db, user=schemas.UserCreate(email=current_user.email, cognito_sub=current_user.email))
    profile = schemas.UserProfileCreate(profile_data=profile_data)
    crud.create_or_update_user_profile(db=db, user_id=user_id, profile=profile)
    response_data = {
        "id": user_id,
        "owner_email": user.email,
        "profile_data": profile_data,
    }
    return JSONResponse(content=response_data)


@app.get("/profile/", response_model=schemas.UserProfile, tags=["User Profile"])
def get_profile_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return Response(
            status_code=204, headers={"X-Profile-Status": "no_user_found"}
        )
    profile_json_str = crud.get_user_profile(db=db, user_id=user_id)
    if profile_json_str is None:
        return Response(
            status_code=204, headers={"X-Profile-Status": "no_profile_found"}
        )
    profile_data = json.loads(profile_json_str)
    profile = schemas.UserProfile(
        id=user_id, owner_email=user.email, profile_data=profile_data
    )
    return JSONResponse(content=profile.model_dump())


@app.get("/jobs/", response_model=List[schemas.Job], tags=["Jobs"])
def get_jobs_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    jobs = crud.get_jobs_for_user(db=db, user_id=user_id)
    return jobs


@app.get("/jobs/{job_id}", response_model=schemas.Job, tags=["Jobs"])
def get_job_endpoint(
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    job = crud.get_job(db=db, job_id=job_id, user_id=user_id)
    if not job:
        raise HTTPException(
            status_code=404, detail=f"Job with id {job_id} not found for user {user_id}"
        )
    return JSONResponse(
        content={
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "description": job.description,
            "user_id": job.user_id,
            "ranking_score": getattr(job, "ranking_score", None),
            "ranking_explanation": getattr(job, "ranking_explanation", None),
            "tailoring_suggestions": getattr(job, "tailoring_suggestions", None),
        }
    )


@app.delete("/jobs/{job_id}", tags=["Jobs"])
async def delete_job_endpoint(
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    success = crud.delete_job(db=db, job_id=job_id, user_id=user_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Job with id {job_id} not found for user {user_id}",
        )
    db.commit()
    await manager.send_personal_message(
        {"job_id": job_id}, user_id, event="job_deleted"
    )
    return {"status": "deleted"}


# --- Endpoint to save job from Chrome Extension --- #
from aws_embedded_metrics import metric_scope

@metric_scope
async def process_job_in_background(
    user_id: int,
    markdown_content: str,
    manager: ConnectionManager,
    db_session_override: Session | None = None,
    metrics=None,
):
    metrics.set_namespace("GreatFitJobs")
    metrics.put_metric("jobs_submitted", 1, "Count")
    metrics.set_property("user_id", user_id)
    job_id = None
    """Background task to process a job description. Can use an override session for testing."""
    db_session: Session | None = None # Initialize
    job_id: int | None = None # To store the job ID once created
    session_created_internally = False # Flag to track if we need to close the session

    try:
        if db_session_override:
            db_session = db_session_override
            logger.info("BG Task: Using provided DB session override.")
        else:
            db_session = SessionLocal() # Create a new session for this task
            session_created_internally = True
            logger.info("BG Task: Created new DB session internally.")

        # --- Get User and Check Credits --- #
        user = crud.get_user_by_id(db=db_session, user_id=user_id)
        if not user:
            raise Exception(f"User {user_id} not found.") # Should not happen if called via authenticated route

        from settings import get_settings
        if get_settings().auth_billing_enabled and user.credits <= 0:
            logger.warning(f"User {user_id} has insufficient credits ({user.credits}) to save job.")
            await manager.send_personal_message(
                {"error": "Insufficient Credits", "message": "You need more credits to save a new job.", "credits_needed": 1},
                user_id,
                event="job_error",
            )
            # Important: return early before processing the job
            return

        # --- 1. Clean Markdown --- #
        logger.info(f"BG Task: Cleaning markdown for user {user_id}")
        cleaned_data: schemas.CleanedJobDescription = await logic.clean_job_description(
            markdown_content
        )
        logger.info(f"BG Task: Markdown cleaned for user {user_id}")

        # --- 2. Create initial job record (no score yet) --- #
        logger.info("BG: creating job row")
        db_job = crud.create_job(
            db=db_session,
            user_id=user_id,
            job=schemas.JobCreate(
                title=cleaned_data.title,
                company=cleaned_data.company,
                description=cleaned_data.cleaned_markdown,
            ),
        )
        db_session.commit()
        db_session.refresh(db_job)
        job_id = db_job.id
        metrics.set_property("job_id", job_id)
        logger.info("BG: created job row", job_id=job_id)

        # --- 2a. Send initial 'job_created' SSE immediately so UI can render pending card --- #
        initial_job_data = {
            "id": db_job.id,
            "title": db_job.title,
            "company": db_job.company,
            "description": db_job.description,
            "user_id": user_id,
        }
        await manager.send_personal_message(initial_job_data, user_id, event="job_created")
        logger.info(f"BG Task: Sent initial 'job_created' SSE for job {job_id}")

        # --- 3. Rank job now that ID exists --- #
        logger.info("BG: ranking job")
        score, explanation = await logic.rank_job_with_llm(
            db=db_session, job_id=db_job.id, user_id=user_id
        )
        if score is not None:
            db_job.ranking_score = score
            db_job.ranking_explanation = explanation
            db_session.commit()
            logger.info(f"BG: updated job {job_id} with ranking score {score}")

            # --- Send 'job_ranked' SSE so UI can update score/explanation incrementally --- #
            await manager.send_personal_message(
                {"job_id": job_id, "score": score, "explanation": explanation},
                user_id,
                event="job_ranked",
            )
            logger.info(f"BG Task: Sent 'job_ranked' SSE for job {job_id}")
        else:
            logger.warning("BG: ranking failed", job_id=job_id)
            await manager.send_personal_message(
                {
                    "job_id": job_id,
                    "error": "ranking_failed",
                    "message": "Failed to rank job description",
                },
                user_id,
                event="job_error",
            )

        # --- 5. Generate Tailoring Suggestions --- #
        logger.info(f"BG Task: Generating tailoring suggestions for job {job_id}")
        suggestions = await logic.generate_tailoring_suggestions(
            job=db_job, db=db_session
        )
        if suggestions:
            logger.info(f"BG Task: Tailoring suggestions generated for job {job_id}")
            # Update the job object in the current session
            db_job.tailoring_suggestions = suggestions

            # --- 6. Deduct Credit & Commit Final Updates & Send 'job_tailored' SSE --- #
            logger.info(f"BG Task: Deducting credit for user {user_id}")
            # Re-fetch user right before modification to ensure we have the session-managed instance
            user_to_update = db_session.get(models.User, user_id)
            if not user_to_update:
                # This should ideally not happen if the initial fetch succeeded
                raise Exception(f"User {user_id} disappeared during processing.")

            user_to_update.credits -= 1 # Deduct credit here
            # db_session.add(user_to_update) # No need to add if fetched via session.get
            db_session.commit() # Commit all changes (job updates + credit deduction)
            metrics.put_metric("jobs_completed", 1, "Count")
            logger.info(f"BG Task: Final updates committed for job {job_id} (including credit deduction)")

            # Send SSE after successful commit
            await manager.send_personal_message(
                {
                    "job_id": job_id,
                    "status": "tailored",
                    "suggestions": suggestions,
                },
                user_id,
                event="job_tailored",
            )
            logger.info(f"BG Task: Sent 'job_tailored' SSE for job {job_id}")
        else:
            # If tailoring fails, still need to commit the job creation and credit deduction
            logger.warning("BG Task: Tailoring suggestions failed", job_id=job_id)
            await manager.send_personal_message(
                {
                    "job_id": job_id,
                    "error": "tailoring_failed",
                    "message": "Failed to generate tailoring suggestions",
                },
                user_id,
                event="job_error",
            )
            # Re-fetch user right before modification here as well
            user_to_update = db_session.get(models.User, user_id)
            if not user_to_update:
                raise Exception(f"User {user_id} disappeared during processing.")

            user_to_update.credits -= 1 # Deduct credit here as well
            # db_session.add(user_to_update) # No need to add if fetched via session.get
            db_session.commit()

    except openai.ContentFilterFinishReasonError as cf_error:
        metrics.put_metric("jobs_failed", 1, "Count")
        print("EXCEPTION cf_error IN BG TASK:\n", "".join(traceback.format_exception(e)), file=sys.stderr)
        logger.error(
            f"BG Task: Content filter error processing job for user {user_id}: {cf_error}",
            exc_info=True,
        )
        await manager.send_personal_message(
            {
                "error": "Content filter triggered",
                "message": "The job description could not be processed due to content filtering.",
            },
            user_id,
            event="job_error",
        )
    except Exception as e:
        print("EXCEPTION IN BG TASK:\n", "".join(traceback.format_exception(e)), file=sys.stderr)
        error_type = type(e).__name__
        logger.error(
            f"BG Task: Error processing job for user {user_id} (Job ID: {job_id}): {error_type} - {e}",
            exc_info=True,
        )
        # Send specific error message to user if job ID exists
        if job_id:
            error_message = f"Failed to fully process job {job_id}. Error: {error_type}"
            event_data = {
                "job_id": job_id,
                "error": error_type,
                "message": error_message,
            }
        else:
            error_message = f"Failed to process job submission. Error: {error_type}"
            event_data = {"error": error_type, "message": error_message}

        await manager.send_personal_message(event_data, user_id, event="job_error")
        # Rollback if a session exists and an error occurred after initial commit
        if db_session:
            try:
                db_session.rollback()
                logger.info(
                    f"BG Task: Rolled back changes for job {job_id} due to error (credits NOT restored)."
                )
                # Note: Credits are *not* restored automatically on rollback here.
                # A more robust system might handle credit restoration explicitly.
            except Exception as rb_err:
                print("EXCEPTION rb_err IN BG TASK:\n", "".join(traceback.format_exception(e)), file=sys.stderr)
                logger.error(
                    f"BG Task: Error during rollback for job {job_id}: {rb_err}",
                    exc_info=True,
                )

    finally:
        logger.info(f"Background job processing finished for user {user_id}.")
        # Decrement processing count now that background task is finished
        try:
            await manager.decrement_processing_count(user_id)
        except Exception as pc_err:
            logger.error("Failed to decrement processing count", user_id=user_id, exc_info=True)
        if session_created_internally and db_session:
            db_session.close()
            logger.info("BG Task: Closed internally created DB session.")

@app.post("/jobs/markdown", status_code=status.HTTP_202_ACCEPTED)
async def create_job_from_markdown(
    markdown_request: schemas.JobMarkdownRequest,  # expects {"markdown_content": "..."}
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Endpoint to create a new job from markdown content."""
    logger = structlog.get_logger(__name__)
    user_id = current_user.id

    markdown_content = markdown_request.markdown_content.strip()
    if not markdown_content:
        logger.warning("Empty markdown_content received", user_id=user_id)
        raise HTTPException(status_code=422, detail="markdown_content cannot be empty")

    logger.info("Received job markdown", markdown_length=len(markdown_content), user_id=user_id)

    # Increment processing counter + launch background task
    await manager.increment_processing_count(user_id)
    await process_job_in_background(user_id, markdown_content, manager)

    logger.info("Job accepted for processing", user_id=user_id)
    return {"status": "accepted"}


# --- Job Ranking and Tailoring Endpoints ---


class JobRankResponse(BaseModel):
    score: Optional[float] = None
    explanation: Optional[str] = None


@app.post(
    "/jobs/{job_id}/rank",
    response_model=JobRankResponse,
    tags=["LLM Features"],
)
async def rank_job_endpoint(
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    score, explanation = await logic.rank_job_with_llm(
        db=db, job_id=job_id, user_id=user_id
    )
    if score is None or explanation is None:
        raise HTTPException(status_code=500, detail="Failed to rank job using LLM")
    db.commit()
    return {"score": score, "explanation": explanation}


@app.post(
    "/jobs/tailor-suggestions", response_model=schemas.TailoringResponse
)
@app.post("/jobs/from_extension")
@app.post("/jobs/from_extension", response_model=schemas.Job)
async def create_job_from_extension(
    raw_job_input: schemas.RawJobInput = Body(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new job from the extension using raw job description and LLM parsing.
    """
    try:
        # Parse the raw job description using LLM
        parsed = await logic.parse_job_description_with_llm(raw_job_input.raw_description)
        # Validate parsed result
        if not parsed or not all(parsed.get(k) for k in ("title", "company", "description")):
            raise HTTPException(
                status_code=422,
                detail="Failed to extract required fields (title, company, description) from job description."
            )
        job_create = schemas.JobCreate(
            title=parsed["title"],
            company=parsed["company"],
            description=parsed["description"],
        )
        job = crud.create_job(db, job=job_create, user_id=current_user.id)
        await manager.send_personal_message(
            schemas.Job.model_validate(job).model_dump(),
            current_user.id,
            event="job_created",
        )
        return job
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")
async def get_tailoring_suggestions_endpoint(
    request_data: schemas.TailoringRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    db_profile = crud.get_user_profile(db, user_id=user_id)
    if db_profile is None:
        raise HTTPException(
            status_code=404, detail=f"User profile not found for user_id {user_id}"
        )
    try:
        suggestions: schemas.TailoringResponse = await logic.get_tailoring_suggestions(
            profile_text=db_profile, job_description=request_data.job_description
        )
        return suggestions
    except Exception as e:
        print(f"Error generating tailoring suggestions: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to generate tailoring suggestions."
        )


# --- Stripe Checkout Session endpoint
@app.post("/billing/checkout-session", tags=["Billing"])
async def create_checkout_session(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    settings: Settings = Depends(get_settings), # Inject Settings
):
    if not settings.stripe_secret_key or not settings.stripe_price_id_50_credits:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe configuration missing",
        )

    stripe.api_key = settings.stripe_secret_key

    # Define the success and cancel URLs
    # Use request.url_for to build absolute URLs
    success_url = request.url_for('billing_success_page')
    cancel_url = request.url_for('billing_cancel_page')

    try:
        logger.info(f"Attempting to create Stripe checkout session for user {current_user.id}")
        session = await stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": settings.stripe_price_id_50_credits,
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{success_url}?session_id={{CHECKOUT_SESSION_ID}}", # Pass session_id if needed later
            cancel_url=str(cancel_url),
            metadata={"user_id": str(current_user.id)}, # Ensure user_id is passed
        )
        logger.info(f"Stripe checkout session created successfully (ID: {session.id}) for user {current_user.id}")
        return {"url": session.url}
    except Exception as e:
        # Use logger.exception to include traceback
        logger.exception(f"Stripe Checkout session creation failed unexpectedly for user {current_user.id}: {e}")
        # Return 500 Internal Server Error for construction issues
        return JSONResponse(
            content={"status": "error", "detail": "Could not create Stripe checkout session"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# --- Billing Success/Cancel Page Routes --- #
@app.get("/billing/success", response_class=HTMLResponse, name="billing_success_page", tags=["Billing"])
async def billing_success_page(request: Request):
    """Serves the billing success page."""
    return templates.TemplateResponse("billing_success.html", {"request": request})


@app.get("/billing/cancel", response_class=HTMLResponse, name="billing_cancel_page", tags=["Billing"])
async def billing_cancel_page(request: Request):
    """Serves the billing cancellation page."""
    return templates.TemplateResponse("billing_cancel.html", {"request": request})


# --- Stripe Webhook Endpoint --- #
@app.post("/billing/webhook", tags=["Billing"])
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings), # Inject Settings
):
    # --- Dependency/Header Checks --- #
    if not settings.stripe_webhook_secret: # Check settings first
        logger.error("Stripe webhook secret not configured in settings.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stripe webhook secret not configured")
    if not stripe_signature:
        logger.warning("Missing Stripe-Signature header.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe-Signature header")

    # --- Main Processing Block --- #
    try:
        payload = await request.body()
        logger.debug("Webhook payload received.")

        # --- Event Construction --- #
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, settings.stripe_webhook_secret
            )
            # Extract event id and type safely for logging (supports dict or StripeObject)
            if isinstance(event, dict):
                event_id = event.get("id")
                event_type = event.get("type")
            else:
                event_id = getattr(event, "id", None)
                event_type = getattr(event, "type", None)

            logger.info(f"Stripe webhook event received: ID={event_id}, Type={event_type}")
        except ValueError as e:
            # Invalid payload
            logger.warning(f"Stripe Webhook Error: Invalid payload - {e}", exc_info=True) # Log as warning, include traceback
            # Return 400 Bad Request for invalid payload
            return JSONResponse(content={"status": "error", "detail": "Invalid payload"}, status_code=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logger.warning(f"Stripe Webhook Error: Invalid signature - {e}", exc_info=True) # Log as warning, include traceback
            # Return 400 Bad Request for invalid signature
            return JSONResponse(content={"status": "error", "detail": "Invalid signature"}, status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Catch any other unexpected error during event construction
            logger.exception(f"Stripe Webhook Error: Unexpected error constructing event - {e}")
            # Return 500 Internal Server Error for construction issues
            return JSONResponse(content={"status": "error", "detail": "Error processing webhook event construction"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- Event Handling --- #
        logger.info(f"Attempting to handle event ID {event_id}, Type {event_type}")
        try:
            logger.info(f"Inside event handling try block for event ID {event_id}")
            if event['type'] == 'checkout.session.completed':
                session = event['data']['object']
                user_id_str = session.get('metadata', {}).get('user_id')

                # Handle missing or invalid user_id (return 200 OK to Stripe)
                if not user_id_str:
                    logger.error("Stripe Webhook Error: Missing user_id in checkout.session.completed metadata")
                    return JSONResponse(content={"status": "error", "detail": "Missing user_id"}, status_code=200)
                try:
                    user_id = int(user_id_str)
                except ValueError:
                    logger.error(f"Stripe Webhook Error: Invalid user_id format '{user_id_str}' in session metadata")
                    return JSONResponse(content={"status": "error", "detail": "Invalid user_id format"}, status_code=200)

                # Process valid user_id
                logger.info(f"Processing checkout.session.completed for user_id: {user_id}")
                try:
                    user = crud.get_user_by_id(db=db, user_id=user_id)
                    if user:
                        user.credits += 50 # TODO: Make this amount configurable?
                        db.add(user)
                        db.commit()
                        db.refresh(user) # Refresh to get updated state
                        logger.info(f"Successfully added 50 credits to user {user_id}. New balance: {user.credits}")
                    else:
                        # User not found in our database. Per Stripe best practice, acknowledge webhook with 200 OK.
                        # We return status "success" (no-op) so that Stripe will not retry, even though no credits were added.
                        logger.warning(
                            f"Stripe Webhook Notice: User {user_id} not found in DB; skipping credit grant but returning success."
                        )
                        return JSONResponse(content={"status": "success"}, status_code=200)
                except Exception as db_err:
                    # Database or other critical error during update (return 500 Internal Server Error)
                    logger.exception(f"Stripe Webhook Error: Database error updating credits for user {user_id}: {db_err}")
                    db.rollback()
                    return JSONResponse(content={"status": "error", "detail": "Database error processing webhook"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                # Unhandled event type (return 200 OK to Stripe)
                logger.info(f"Stripe Webhook: Received unhandled event type {event_type}")
                # No error, just noting it was unhandled.

        except Exception as e:
            # Catchall for unexpected errors during event *handling*
            logger.exception(f"Stripe Webhook Error: Unexpected error handling event ID {event_id}, Type {event_type}: {e}")
            # Return 500 Internal Server Error for unexpected handling errors
            return JSONResponse(content={"status": "error", "detail": "Internal server error handling webhook event"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # If we reach here, event was handled or ignored gracefully.
        logger.info(f"Webhook processing finished successfully for event ID {event_id}")
        return JSONResponse(content={"status": "success"}, status_code=200)

    except Exception as e:
        # Catch any unexpected error in the *entire* function body (after dep checks)
        logger.exception(f"Unhandled exception in stripe_webhook endpoint: {e}")
        # Ensure a 500 response is sent
        return JSONResponse(
            content={"status": "error", "detail": "An unexpected internal server error occurred."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# --- SSE Endpoint --- #
from auth import verify_token  # already present
from database import SessionLocal

@app.get("/stream-jobs")
async def stream_jobs(request: Request, token: str | None = None, user_id: int | None = None):
    """Endpoint for Server-Sent Events to stream new job updates."""
    logger = structlog.get_logger("uvicorn.error")
    settings = get_settings()
    if token:
        try:
            payload = verify_token(token)
            with SessionLocal() as db:
                import crud  # avoid circular import at top
                user = crud.get_user_by_email(db, payload.email or payload.sub)
                if not user:
                    logger.warning("SSE 401: Unknown user in token", extra={"token": token})
                    raise HTTPException(401, "Unknown user in token")
                user_id = user.id
                logger.info("SSE auth ok", extra={"user_id": user_id})
        except Exception as e:
            logger.warning(f"SSE 401: Token verification failed: {e}", extra={"token": token})
            raise HTTPException(401, "Invalid or expired token")
    else:
        if settings.auth_billing_enabled:
            # In auth-enabled mode, token is mandatory
            logger.warning("SSE 401: No token provided while auth is enabled")
            raise HTTPException(401, "No token provided")
        # Auth disabled (local dev) – allow connecting via user_id query param
        if user_id is None:
            logger.warning("SSE 401: Missing user_id in local mode")
            raise HTTPException(401, "user_id query parameter required in local mode")
        # In local mode, trust the provided user_id
        logger.info("SSE local mode auth ok", extra={"user_id": user_id})
    queue = await manager.connect(user_id)
    async def event_generator():
        try:
            while True:
                message_dict = await queue.get()
                if await request.is_disconnected():
                    logger.info(
                        f"SSE client disconnected for user {user_id} before sending."
                    )
                    break
                yield message_dict
        except asyncio.CancelledError:
            logger.info(f"SSE connection cancelled for user {user_id}")
        finally:
            manager.disconnect(user_id)
    return EventSourceResponse(event_generator())


# --- Main execution --- (for running with uvicorn)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
