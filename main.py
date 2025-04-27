import asyncio
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Path,
    UploadFile,
    File,
    Request,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response, HTMLResponse
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

import models
import schemas
import crud
import logic
from database import SessionLocal, create_db_and_tables, get_db
from auth import get_current_user, AUTH_ENABLED

# Initialise observability before creating app
init_observability()

# Create DB tables on startup
create_db_and_tables()

app = FastAPI(
    title="Great Fit",
    description="Backend API for Great Fit job application assistant",
    version="0.1.0",
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info(f"SSE connection established for user {user_id}")
        return queue

    def disconnect(self, user_id: int):
        """Removes a user's queue when they disconnect."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"SSE connection closed for user {user_id}")

    async def send_personal_message(
        self, message: str, user_id: int, event: str = "message"
    ):
        """Sends a message to a specific user's queue."""
        if user_id in self.active_connections:
            json_data = json.dumps(message)
            await self.active_connections[user_id].put(
                {"event": event, "data": json_data}
            )
            logger.info(f"Sent SSE event '{event}' to user {user_id}")
        else:
            logger.warning(f"Attempted to send SSE to disconnected user {user_id}")

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
            logger.info(f"Incremented processing count for user {user_id} to {count}")

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
            logger.info(f"Decremented processing count for user {user_id} to {count}")
        elif user_id in self.processing_counts and self.processing_counts[user_id] <= 0:
            logger.info(f"Processing count for user {user_id} is already 0")


manager = ConnectionManager()


# --- Root Endpoint --- Serve index page with Jinja2 Template --- #
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Render the main index page.

    Uses Jinja2 template rendering instead of serving a static file so that we
    can progressively migrate to server‑side rendering with HTMX and Alpine.js
    in the frontend.
    """
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "env": "dev",
            "cognito_app_client_id": os.getenv("COGNITO_APP_CLIENT_ID", ""),
            "cognito_domain": os.getenv("COGNITO_DOMAIN", ""),
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
@app.post(
    "/users/{user_id}/profile/",
    response_model=schemas.UserProfile,
    tags=["User Profile"],
)
def create_or_update_profile_endpoint(
    user_id: int,
    profile: schemas.UserProfileCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operation not permitted for this user")

    # Check if the user exists in the database
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        # User doesn't exist, create new user
        user = crud.create_user(
            db=db, user=schemas.UserCreate(email="user@example.com")
        )

    crud.create_or_update_user_profile(db=db, user_id=user_id, profile=profile)
    # Retrieve the updated profile to return it
    profile_json_str = crud.get_user_profile(db=db, user_id=user_id)
    if profile_json_str is None:
        # User exists but has no profile
        return Response(
            status_code=204,  # No Content
            headers={"X-Profile-Status": "no_profile_found"},
        )

    # Normal case - return the profile
    profile_data = json.loads(profile_json_str)
    return schemas.UserProfile(
        id=user_id, owner_email=user.email, profile_data=profile_data
    )


@app.post("/users/{user_id}/resume/upload", tags=["User Profile"])
async def upload_resume_endpoint(
    user_id: int,
    resume: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operation not permitted for this user")

    # Extract text from the resume file
    resume_text = await extract_text_from_resume(resume)

    if not resume_text.strip():
        raise HTTPException(
            status_code=400, detail="Could not extract text from the resume"
        )

    # Parse the resume text using LLM
    profile_data = await logic.parse_resume_with_llm(resume_text)

    # Check if the user exists in the database
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        # User doesn't exist, create new user
        user = crud.create_user(
            db=db, user=schemas.UserCreate(email="user@example.com")
        )

    # Create or update the user profile with the parsed data
    profile = schemas.UserProfileCreate(profile_data=profile_data)
    crud.create_or_update_user_profile(db=db, user_id=user_id, profile=profile)

    # Create the response object and return as JSON
    response_data = {
        "id": user_id,
        "owner_email": user.email,
        "profile_data": profile_data,
    }

    return JSONResponse(content=response_data)


@app.get("/users/{user_id}/profile/", response_model=schemas.UserProfile, tags=["User Profile"])
def get_profile_endpoint(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operation not permitted for this user")

    # Check if user exists first
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        # Return a custom response for no user
        return Response(
            status_code=204, headers={"X-Profile-Status": "no_user_found"}  # No Content
        )

    # Now check for profile
    profile_json_str = crud.get_user_profile(db=db, user_id=user_id)
    if profile_json_str is None:
        # User exists but has no profile
        return Response(
            status_code=204,  # No Content
            headers={"X-Profile-Status": "no_profile_found"},
        )

    # Normal case - return the profile
    profile_data = json.loads(profile_json_str)
    profile = schemas.UserProfile(
        id=user_id, owner_email=user.email, profile_data=profile_data
    )

    # Convert to dictionary and return as JSON response
    return JSONResponse(content=profile.model_dump())


@app.get("/users/{user_id}/jobs/", response_model=List[schemas.Job], tags=["Jobs"])
def get_jobs_endpoint(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operation not permitted for this user")
    jobs = crud.get_jobs_for_user(db=db, user_id=user_id)
    return jobs


@app.get("/users/{user_id}/jobs/{job_id}", response_model=schemas.Job, tags=["Jobs"])
def get_job_endpoint(
    user_id: int,
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a specific job by ID for a user
    """
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


@app.delete("/users/{user_id}/jobs/{job_id}", tags=["Jobs"])
async def delete_job_endpoint(
    user_id: int,
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user.id:  # keep existing auth guard
        raise HTTPException(
            status_code=403, detail="Operation not permitted for this user"
        )

    success = crud.delete_job(db=db, job_id=job_id, user_id=user_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Job with id {job_id} not found for user {user_id}",
        )
    db.commit()

    # Notify front‑end via SSE
    await manager.send_personal_message(
        {"job_id": job_id}, user_id, event="job_deleted"
    )
    return {"status": "deleted"}


# --- Endpoint to save job from Chrome Extension --- #
async def process_job_in_background(
    user_id: int, markdown_content: str, manager: ConnectionManager
):
    """
    Processes job cleaning, saving, ranking, and notification in the background.
    Manages its own database session and uses a semaphore for SQLite write safety.
    """
    logger.info("Background job processing starting.")

    db_session: Session | None = None
    job_id: int | None = None
    created_job_data = {}

    try:
        # --- 1. Clean Markdown --- #
        logger.info(f"BG Task: Cleaning markdown for user {user_id}")
        cleaned_data: schemas.CleanedJobDescription = await logic.clean_job_description(
            markdown_content
        )
        logger.info(f"BG Task: Markdown cleaned for user {user_id}")

        # --- 2. Create Initial Job Record --- #
        logger.info(f"BG Task: Creating initial job record for user {user_id}")
        db_session = SessionLocal()
        db_job = crud.create_job(
            db=db_session,
            user_id=user_id,
            job=schemas.JobCreate(
                title=cleaned_data.title,
                company=cleaned_data.company,
                description=cleaned_data.cleaned_markdown,
                # ranking_score, ranking_explanation, tailoring_suggestions are initially null
            ),
        )
        db_session.commit()
        db_session.refresh(db_job)
        job_id = db_job.id
        logger.info(
            f"BG Task: Initial job record created (ID: {job_id}) for user {user_id}"
        )

        # Prepare data for SSE event
        created_job_data = schemas.Job.model_validate(db_job).model_dump()

        # --- 3. Send 'job_created' SSE --- #
        await manager.send_personal_message(
            created_job_data, user_id, event="job_created"
        )
        logger.info(f"BG Task: Sent 'job_created' SSE for job {job_id}")

        # --- 4. Rank Job --- #
        logger.info(f"BG Task: Ranking job {job_id} for user {user_id}")
        score, explanation = await logic.rank_job_with_llm(
            db=db_session, job_id=job_id, user_id=user_id
        )
        if score is None or explanation is None:
            # Log error but continue to tailoring if possible
            logger.error(
                f"BG Task: Failed to rank job {job_id}. Proceeding without ranking."
            )
            score = None
            explanation = None
        else:
            logger.info(f"BG Task: Job {job_id} ranked. Score: {score}")
            # Update the job object in the current session (will be committed later)
            db_job.ranking_score = score
            db_job.ranking_explanation = explanation

            # --- 5. Send 'job_ranked' SSE --- #
            await manager.send_personal_message(
                {"job_id": job_id, "score": score, "explanation": explanation},
                user_id,
                event="job_ranked",
            )
            logger.info(f"BG Task: Sent 'job_ranked' SSE for job {job_id}")

        # --- 6. Generate Tailoring Suggestions --- #
        logger.info(f"BG Task: Generating tailoring suggestions for job {job_id}")
        suggestions = await logic.generate_tailoring_suggestions(
            job=db_job, db=db_session
        )
        if suggestions:
            logger.info(f"BG Task: Tailoring suggestions generated for job {job_id}")
            # Update the job object in the current session
            db_job.tailoring_suggestions = suggestions

            # --- 7. Commit Final Updates & Send 'job_tailored' SSE --- # (Commit happens here)
            db_session.commit()
            logger.info(f"BG Task: Final updates committed for job {job_id}")

            await manager.send_personal_message(
                {"job_id": job_id, "suggestions": suggestions},
                user_id,
                event="job_tailored",
            )
            logger.info(f"BG Task: Sent 'job_tailored' SSE for job {job_id}")
        else:
            # Only commit ranking if tailoring failed but ranking succeeded
            if score is not None:
                db_session.commit()
                logger.info(
                    f"BG Task: Ranking update committed for job {job_id} (tailoring failed)."
                )
            logger.warning(
                f"BG Task: Failed to generate tailoring suggestions for job {job_id}. Skipping tailoring update."
            )

    except openai.ContentFilterFinishReasonError as cf_error:
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
        if db_session and job_id:
            try:
                db_session.rollback()
                logger.info(
                    f"BG Task: Rolled back changes for job {job_id} due to error."
                )
            except Exception as rb_err:
                logger.error(
                    f"BG Task: Error during rollback for job {job_id}: {rb_err}",
                    exc_info=True,
                )

    finally:
        logger.info(f"Background job processing finished for user {user_id}.")
        if db_session:
            db_session.close()
        await manager.decrement_processing_count(user_id)


# --- Endpoint to save job from Chrome Extension --- #
@app.post(
    "/users/{user_id}/jobs/from_extension",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Jobs", "Extension"],
)
async def save_job_from_extension(
    user_id: int,
    markdown_request: schemas.JobMarkdownRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operation not permitted for this user")
    print(f"DEBUG: Entering save_job_from_extension for user {user_id}")
    logger.info(
        f"Endpoint: Received job markdown request from extension for user {user_id}. Scheduling background processing."
    )

    # Increment count immediately for faster UI feedback that the request was received
    await manager.increment_processing_count(user_id)

    # Schedule the actual processing to run in the background
    background_tasks.add_task(
        process_job_in_background, user_id, markdown_request.markdown_content, manager
    )

    # Return an immediate response indicating acceptance
    logger.info(f"Endpoint: Responding 202 Accepted for user {user_id} job submission.")
    return {
        "message": "Job submission received and is being processed in the background."
    }


# --- Job Ranking and Tailoring Endpoints ---


class JobRankResponse(BaseModel):
    score: Optional[float] = None
    explanation: Optional[str] = None


@app.post(
    "/users/{user_id}/jobs/{job_id}/rank",
    response_model=JobRankResponse,
    tags=["LLM Features"],
)
async def rank_job_endpoint(
    user_id: int,
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Operation not permitted for this user")
    """Triggers LLM ranking for a specific job based on user 1's profile."""
    # user_id is now a parameter, no need to hardcode
    score, explanation = await logic.rank_job_with_llm(
        db=db, job_id=job_id, user_id=user_id
    )
    if score is None or explanation is None:
        raise HTTPException(status_code=500, detail="Failed to rank job using LLM")

    db.commit()

    return {"score": score, "explanation": explanation}


@app.post(
    "/users/{user_id}/jobs/tailor-suggestions", response_model=schemas.TailoringResponse
)
async def get_tailoring_suggestions_endpoint(
    request_data: schemas.TailoringRequest,
    user_id: int = Path(..., title="The ID of the user to get suggestions for"),
    db: Session = Depends(get_db),
):
    """
    Generates tailoring suggestions for a given job description based on the user's profile.
    """
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


# --- SSE Endpoint --- #
@app.get("/stream-jobs/{user_id}")
async def stream_jobs(
    request: Request,
    user_id: int,
    token: str | None = None,
):
    """Endpoint for Server-Sent Events to stream new job updates."""
    if AUTH_ENABLED:
        if token is None:
            raise HTTPException(status_code=401, detail="Missing token for SSE")

        from auth import verify_token

        payload = verify_token(token)

        # Validate that the token owner matches path param by looking up the user record
        db = SessionLocal()
        try:
            user = crud.get_user_by_email(db, payload.email or payload.sub)
            if not user or user.id != user_id:
                raise HTTPException(status_code=403, detail="Token/user mismatch")
        finally:
            db.close()

    queue = await manager.connect(user_id)

    async def event_generator():
        try:
            while True:
                # Wait for a message in the queue
                message_dict = await queue.get()
                if await request.is_disconnected():
                    logger.info(
                        f"SSE client disconnected for user {user_id} before sending."
                    )
                    break
                # Yield the event in SSE format
                yield message_dict
        except asyncio.CancelledError:
            logger.info(f"SSE connection cancelled for user {user_id}")
        finally:
            manager.disconnect(user_id)

    return EventSourceResponse(event_generator())


# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Main execution --- (for running with uvicorn)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
