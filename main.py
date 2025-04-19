from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Path,
    UploadFile,
    File,
    Request,
    Form,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
import json
from pydantic import BaseModel
import os
import tempfile
from fastapi import status
import fitz
from docx import Document
import logging
import asyncio
from sse_starlette.sse import EventSourceResponse
import json

import models, schemas, crud, logic, llm_interaction
from database import SessionLocal, engine, create_db_and_tables, get_db

# Create DB tables on startup
create_db_and_tables()

app = FastAPI(
    title="Job Application Assistant PoC",
    description="Backend API for the Job Application Assistant PoC",
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


# --- Root Endpoint --- Serve index.html using FileResponse
@app.get("/", response_class=FileResponse)
async def read_root():
    index_path = "static/index.html"
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path, media_type="text/html")


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
    user_id: int, profile: schemas.UserProfileCreate, db: Session = Depends(get_db)
):
    if user_id != 1:
        raise HTTPException(
            status_code=403, detail="Operation not permitted for this user"
        )

    # Check if the user exists in the database
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        # User doesn't exist, create new user
        user = crud.create_user(
            db=db, user=schemas.UserCreate(email="user@example.com")
        )

    user_profile = crud.create_or_update_user_profile(
        db=db, user_id=user_id, profile=profile
    )
    return schemas.UserProfile(
        id=user_id, owner_email=user.email, profile_data=profile.profile_data
    )


@app.post("/users/{user_id}/resume/upload", tags=["User Profile"])
async def upload_resume_endpoint(
    user_id: int, resume: UploadFile = File(...), db: Session = Depends(get_db)
):
    """Upload and parse a resume to create user profile"""

    if user_id != 1:
        raise HTTPException(
            status_code=403, detail="Operation not permitted for this user"
        )

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
    user_profile = crud.create_or_update_user_profile(
        db=db, user_id=user_id, profile=profile
    )

    # Create the response object and return as JSON
    response_data = {
        "id": user_id,
        "owner_email": user.email,
        "profile_data": profile_data,
    }

    return JSONResponse(content=response_data)


@app.get("/users/{user_id}/profile/", tags=["User Profile"])
def get_profile_endpoint(user_id: int, db: Session = Depends(get_db)):
    if user_id != 1:
        raise HTTPException(
            status_code=403, detail="Operation not permitted for this user"
        )

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


# --- Job Endpoints (Assuming user_id=1 for PoC) ---
@app.post("/users/{user_id}/jobs/", tags=["Jobs"])
async def create_job_endpoint(
    user_id: int, job: schemas.JobCreate, db: Session = Depends(get_db)
):
    # Verify user exists
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Format the job description with LLM
    formatted_job_data = await logic.format_job_details_with_llm(job.description)

    # Update the job description with formatted content
    enhanced_job = schemas.JobCreate(
        title=formatted_job_data.get("title", job.title) or job.title,
        company=formatted_job_data.get("company", job.company) or job.company,
        description=json.dumps(
            formatted_job_data
        ),  # Store the full formatted data as JSON
    )

    # Create the job with enhanced data
    created_job = crud.create_job(db=db, job=enhanced_job, user_id=user_id)

    # Return response as JSONResponse to avoid validation issues
    return JSONResponse(
        content={
            "id": created_job.id,
            "title": created_job.title,
            "company": created_job.company,
            "description": created_job.description,
            "user_id": created_job.user_id,
        }
    )


@app.get("/users/{user_id}/jobs/", response_model=List[schemas.Job], tags=["Jobs"])
def get_jobs_endpoint(user_id: int, db: Session = Depends(get_db)):
    if user_id != 1:
        raise HTTPException(
            status_code=403, detail="Operation not permitted for this user"
        )
    jobs = crud.get_jobs_for_user(db=db, user_id=user_id)
    return jobs


@app.get("/users/{user_id}/jobs/{job_id}", tags=["Jobs"])
def get_job_endpoint(user_id: int, job_id: int, db: Session = Depends(get_db)):
    """
    Get a specific job by ID for a user
    """
    job = crud.get_job(db=db, job_id=job_id, user_id=user_id)
    if not job:
        raise HTTPException(
            status_code=404, detail=f"Job with id {job_id} not found for user {user_id}"
        )

    # Return as JSONResponse for consistency with other endpoints
    return JSONResponse(
        content={
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "description": job.description,
            "user_id": job.user_id,
            # Include any additional fields that might be in the response model
            "ranking_score": getattr(job, "ranking_score", None),
            "ranking_explanation": getattr(job, "ranking_explanation", None),
        }
    )


@app.delete("/users/{user_id}/jobs/{job_id}", tags=["Jobs"])
def delete_job_endpoint(user_id: int, job_id: int, db: Session = Depends(get_db)):
    """
    Delete a specific job by ID for a user
    """
    # For demo purposes, only allow user 1 to delete jobs
    if user_id != 1:
        raise HTTPException(
            status_code=403, detail="Operation not permitted for this user"
        )

    # Attempt to delete the job
    success = crud.delete_job(db=db, job_id=job_id, user_id=user_id)

    if not success:
        raise HTTPException(
            status_code=404, detail=f"Job with id {job_id} not found for user {user_id}"
        )

    return {"message": "Job deleted successfully"}


# --- New Job Parsing/Saving Endpoint ---
@app.post("/jobs/parse-and-save/", response_model=schemas.Job, tags=["Jobs"])
async def parse_and_create_job_endpoint(
    job_input: schemas.JobDescriptionInput,  # Expect raw description
    user_id: int = 1,  # Hardcoded user ID for PoC
    db: Session = Depends(get_db),
):
    """POC endpoint to parse job description and save it as a new job."""
    logger.info(f"Received job description for user {user_id}.")

    try:
        # 1. Extract title and company using LLM
        logger.debug("Calling LLM to extract job info...")
        extracted_info = await logic.extract_job_info_with_llm(job_input.description)

        # 2. Prepare data for CRUD operation
        job_data_to_create = schemas.JobCreate(
            title=extracted_info.title,  # Use extracted title
            company=extracted_info.company,  # Use extracted company
            description=job_input.description,  # Use original full text
            # user_id is handled by crud.create_job
        )

        # 3. Create job in the database
        logger.debug(f"Creating job entry for user {user_id}...")
        db_job = crud.create_job(db=db, job=job_data_to_create, user_id=user_id)
        logger.info(f"Successfully saved job '{db_job.title}' for user {user_id}.")

        # --- Send SSE event --- #
        try:
            # Serialize the created/updated job data for the frontend
            # We need to manually convert the SQLAlchemy model to a dict/JSON compatible format
            # Using the Pydantic schema ensures consistency
            job_response_data = schemas.Job.model_validate(db_job)
            job_json = job_response_data.model_dump_json()
            await manager.send_personal_message(job_json, user_id, event="new_job")
        except Exception as sse_error:
            logger.error(f"Error sending SSE event for user {user_id}: {sse_error}")
            # Don't fail the request if SSE fails, just log it

        return job_response_data

    except Exception as e:
        logger.error(f"Error processing job for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save job: {str(e)}")


# --- Endpoint to save job from Chrome Extension --- #
async def process_job_in_background(
    user_id: int, markdown_content: str, manager: ConnectionManager
):
    """
    Processes job cleaning, saving, ranking, and notification in the background.
    Manages its own database session and uses a semaphore for SQLite write safety.
    """
    job_id_for_logging = "N/A"
    final_job_data_for_sse = None
    try:
        # --- LLM Call 1: Clean Markdown (Outside DB lock) ---
        logger.debug(
            f"BG Task: Calling LLM to clean job markdown for user {user_id}..."
        )
        cleaned_data = await llm_interaction.call_llm_to_clean_job_markdown(
            markdown_content
        )
        logger.info(f"BG Task: LLM cleaning finished for user {user_id}.")

        async with db_write_semaphore:  # <-- Acquire semaphore ONLY for DB writes
            db: Session | None = None
            try:
                db = SessionLocal()

                # --- Get User (Inside lock, before writes) ---
                user = crud.get_user_by_id(db, user_id=user_id)
                if user is None:
                    logger.error(
                        f"BG Task: User {user_id} not found. Aborting job processing."
                    )
                    # No need to decrement count here, outer finally handles it.
                    return  # Exit early
                # --- Create Job Entry (Inside DB lock) ---
                logger.debug(f"BG Task: Creating job entry for user {user_id}...")
                job_data_to_create = schemas.JobCreate(
                    title=cleaned_data.title or "Unknown Title",
                    company=cleaned_data.company or "Unknown Company",
                    location=cleaned_data.location,
                    description=cleaned_data.cleaned_markdown or markdown_content,
                    url=cleaned_data.url,
                    user_id=user.id,
                    raw_markdown=markdown_content,
                )
                db_job = crud.create_job(db=db, job=job_data_to_create, user_id=user_id)
                job_id_for_logging = db_job.id
                logger.info(
                    f"BG Task: Successfully created job '{db_job.title}' (ID: {db_job.id}) for user {user_id}."
                )

                # --- Rank Job (LLM Call + DB Update inside Lock) ---
                logger.info(
                    f"BG Task: Calling LLM to rank job '{db_job.title}' (ID: {db_job.id}) for user {user_id}."
                )
                score, explanation = await logic.rank_job_with_llm(
                    db, db_job.id, user_id
                )
                if score is not None:
                    logger.info(
                        f"BG Task: Successfully ranked job '{db_job.title}' (ID: {db_job.id}). Score: {score}"
                    )
                else:
                    logger.warning(
                        f"BG Task: LLM Ranking failed or skipped for job {db_job.id}"
                    )

                # --- Commit Transaction (Inside Lock) ---
                db.commit()
                logger.info(f"BG Task: Committed transaction for job {db_job.id}.")

                # Refresh db_job to get final state after commit (Inside Lock)
                db.refresh(db_job)
                # Prepare data for SSE *after* commit and refresh
                final_job_data_for_sse = schemas.Job.model_validate(db_job)

            except Exception as db_error:  # Catch errors within the lock separately
                logger.error(
                    f"BG Task: Error during DB operations for job (ID: {job_id_for_logging}) user {user_id}: {db_error}",
                    exc_info=True,
                )
                # Send error notification via SSE (if manager available)
                await manager.send_personal_message(
                    {"error": str(db_error), "job_id": job_id_for_logging},
                    user_id,
                    event="processing_error",
                )
                logger.info(f"Sent SSE event 'processing_error' to user {user_id}")
                final_job_data_for_sse = None  # Ensure we don't send success SSE
            finally:
                if db:  # Close session if created
                    db.close()
        # --- Semaphore released here ---
        # --- Send SSE Notification (Outside DB lock) ---
        if final_job_data_for_sse:
            logger.info(
                f"BG Task: Sending 'job_processed' event for job {final_job_data_for_sse.id} to user {user_id}"
            )
            await manager.send_personal_message(
                final_job_data_for_sse.model_dump(), user_id, event="job_processed"
            )

    except Exception as e:
        # Catch errors happening *outside* the DB lock (e.g., initial LLM call)
        logger.error(
            f"BG Task: General error processing job for user {user_id}: {e}",
            exc_info=True,
        )
        await manager.send_personal_message(
            {
                "error": str(e),
                "job_id": job_id_for_logging,
            },  # job_id might still be N/A
            user_id,
            event="processing_error",
        )
        logger.info(f"Sent SSE event 'processing_error' to user {user_id}")

    finally:
        # Decrement count regardless of success/failure, inside/outside lock
        await manager.decrement_processing_count(user_id)
        logger.debug(
            f"BG Task: Decremented processing count for user {user_id}. Job ID attempted: {job_id_for_logging}"
        )


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
    # Removed db: Session = Depends(get_db)
):
    """
    Accepts job markdown from the extension, increments the processing count immediately,
    schedules the full processing (cleaning, saving, ranking) in the background,
    and returns an immediate 202 Accepted response.
    """
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
from pydantic import BaseModel
from typing import Optional


class JobRankResponse(BaseModel):
    score: Optional[float] = None
    explanation: Optional[str] = None


@app.post(
    "/users/{user_id}/jobs/{job_id}/rank",
    response_model=JobRankResponse,
    tags=["LLM Features"],
)
async def rank_job_endpoint(user_id: int, job_id: int, db: Session = Depends(get_db)):
    """Triggers LLM ranking for a specific job based on user 1's profile."""
    # user_id is now a parameter, no need to hardcode
    score, explanation = await logic.rank_job_with_llm(
        db=db, job_id=job_id, user_id=user_id
    )
    if score is None or explanation is None:
        raise HTTPException(status_code=500, detail="Failed to rank job using LLM")

    db.commit()

    return {"score": score, "explanation": explanation}


# --- Autofill Mapping Endpoint ---
@app.post("/autofill/map_poc", response_model=Dict[str, str], tags=["Autofill"])
async def map_autofill_fields_poc(
    form_fields: List[schemas.FormFieldInfo],
    user_id: int = 1,
    db: Session = Depends(get_db),
):
    """POC endpoint to map user profile data to given form fields using LLM.

    First checks if the user profile exists before attempting to use LLM.
    """
    profile_json_str = crud.get_user_profile(db=db, user_id=user_id)
    if profile_json_str is None:
        raise HTTPException(
            status_code=404, detail=f"Profile not found for user {user_id}"
        )

    try:
        mapping = await logic.map_form_fields_with_llm(
            db=db, user_id=user_id, form_fields=form_fields
        )
        return mapping
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to map autofill fields: {e}"
        )


# --- New Endpoint ---
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
async def stream_jobs(request: Request, user_id: int):
    """Endpoint for Server-Sent Events to stream new job updates."""
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
