from fastapi import FastAPI, Depends, HTTPException, Path, UploadFile, File, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
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

import models, schemas, crud, logic, llm_interaction
from database import SessionLocal, create_db_and_tables, get_db

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
        return db_job

    except Exception as e:
        logger.error(f"Error processing job for user {user_id}: {e}", exc_info=True)
        # Consider more specific error handling (e.g., LLM failure vs. DB error)
        raise HTTPException(
            status_code=500, detail=f"Failed to save job: {str(e)}"
        )


# --- Endpoint to save job from Chrome Extension --- #
@app.post("/users/{user_id}/jobs/from_extension", response_model=schemas.Job, tags=["Jobs", "Extension"])
async def save_job_from_extension(
    user_id: int,
    request: schemas.JobMarkdownRequest,
    db: Session = Depends(get_db),
):
    """Receives raw job markdown from the Chrome extension, cleans it using LLM, and saves it as a new job."""
    logger.info(f"Received job markdown from extension for user {user_id}.")
    # Use the correct function to get user by ID
    user = crud.get_user_by_id(db, user_id=user_id)
    if user is None:
        logger.error(f"User with ID {user_id} not found.")
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Call the LLM cleaning function from the correct module
        cleaned_data: schemas.CleanedJobDescription = await llm_interaction.call_llm_to_clean_job_markdown(
            markdown_content=request.markdown_content
        )

        # Create the JobCreate object using data from the cleaned LLM output
        job_data = schemas.JobCreate(
            title=cleaned_data.title or "Unknown Title",
            company=cleaned_data.company or "Unknown Company",
            location=cleaned_data.location or "Unknown Location",
            url=cleaned_data.url or "",
            description=cleaned_data.cleaned_markdown,
            status="Bookmarked", # Default status for jobs from extension
            notes="Added via Chrome Extension",
            user_id=user_id # Ensure user_id is passed correctly
        )

        # Save the job using the correct CRUD function
        db_job = crud.create_job(db=db, job=job_data, user_id=user_id)

        # --- LLM Ranking (Moved after job creation) --- #
        # Combine profile data and job description for ranking
        logger.info(f"Calling LLM to rank job '{db_job.title}' for user {user_id}.")
        score, explanation = await logic.rank_job_with_llm(
            db=db, job_id=db_job.id, user_id=user_id
        )
        if score is None or explanation is None:
            raise HTTPException(status_code=500, detail="Failed to rank job using LLM")

        db.commit()

        logger.info(f"Successfully ranked job '{db_job.title}' for user {user_id}.")
        return db_job

    except Exception as e:
        logger.error(f"Error processing job from extension for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save job from extension: {e}"
        )


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


class ResumeTailoringRequest(BaseModel):
    job_description: str
    profile_snippet: str


class ResumeTailoringResponse(BaseModel):
    suggestions: Optional[str] = None


@app.post(
    "/resume/suggest_tailoring",
    response_model=ResumeTailoringResponse,
    tags=["LLM Features"],
)
async def suggest_tailoring_endpoint(request: ResumeTailoringRequest):
    """Generates resume tailoring suggestions based on job description and profile snippet."""
    suggestions = await logic.suggest_resume_tailoring(
        job_description=request.job_description, profile_snippet=request.profile_snippet
    )
    if suggestions is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate resume tailoring suggestions using LLM",
        )
    return {"suggestions": suggestions}


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
@app.post("/users/{user_id}/jobs/tailor-suggestions", response_model=schemas.TailoringResponse)
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
        suggestions = await logic.get_tailoring_suggestions(
            profile_text=db_profile, job_description=request_data.job_description
        )
        return schemas.TailoringResponse(suggestions=suggestions)
    except Exception as e:
        print(f"Error generating tailoring suggestions: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to generate tailoring suggestions."
        )


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
