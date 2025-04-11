from fastapi import FastAPI, Depends, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Dict
import json
from pydantic import BaseModel
import os
from fastapi import Response, status

import models, schemas, crud, logic
from database import SessionLocal, create_db_and_tables, get_db

# Create DB tables on startup
create_db_and_tables()

app = FastAPI(
    title="Job Application Assistant PoC",
    description="Backend API for the Job Application Assistant PoC",
    version="0.1.0"
)

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
    return FileResponse(index_path, media_type='text/html')

# Add route for favicon.ico
@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- User Endpoints ---
@app.post("/users/", response_model=schemas.User, tags=["Users"])
def create_user_endpoint(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)

# --- User Profile Endpoints (Assuming user_id=1 for PoC) ---
@app.post("/users/{user_id}/profile/", response_model=schemas.UserProfile, tags=["User Profile"])
def create_or_update_profile_endpoint(user_id: int, profile: schemas.UserProfileCreate, db: Session = Depends(get_db)):
    profile_json_str = crud.create_or_update_user_profile(db=db, user_id=user_id, profile=profile)
    if profile_json_str is None:
        raise HTTPException(status_code=404, detail="User not found")

    profile_data = json.loads(profile_json_str)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
         raise HTTPException(status_code=404, detail="User not found after profile update")

    return schemas.UserProfile(id=user_id, owner_email=user.email, profile_data=profile_data)

@app.get("/users/{user_id}/profile/", response_model=schemas.UserProfile, tags=["User Profile"])
def get_profile_endpoint(user_id: int, db: Session = Depends(get_db)):
    if user_id != 1:
         raise HTTPException(status_code=403, detail="Operation not permitted for this user")

    profile_json_str = crud.get_user_profile(db=db, user_id=user_id)
    if profile_json_str is None:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        else:
             raise HTTPException(status_code=404, detail="User profile not found")

    profile_data = json.loads(profile_json_str)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found when retrieving email for profile")

    return schemas.UserProfile(id=user_id, owner_email=user.email, profile_data=profile_data)

# --- Job Endpoints (Assuming user_id=1 for PoC) ---
@app.post("/users/{user_id}/jobs/", response_model=schemas.Job, tags=["Jobs"])
def create_job_endpoint(user_id: int, job: schemas.JobCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.create_job(db=db, job=job, user_id=user_id)

@app.get("/users/{user_id}/jobs/", response_model=List[schemas.Job], tags=["Jobs"])
def get_jobs_endpoint(user_id: int, db: Session = Depends(get_db)):
    if user_id != 1:
         raise HTTPException(status_code=403, detail="Operation not permitted for this user")
    jobs = crud.get_jobs_for_user(db=db, user_id=user_id)
    return jobs

@app.get("/users/{user_id}/jobs/{job_id}", response_model=schemas.Job, tags=["Jobs"])
def get_job_endpoint(user_id: int, job_id: int, db: Session = Depends(get_db)):
    """
    Get a specific job by ID for a user
    """
    job = crud.get_job(db=db, job_id=job_id, user_id=user_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with id {job_id} not found for user {user_id}")
    return job

# --- New Job Parsing/Saving Endpoint ---
@app.post("/jobs/parse-and-save/", response_model=schemas.Job, tags=["Jobs"])
async def parse_and_create_job_endpoint(
    job_input: schemas.JobDescriptionInput, # Expect raw description
    user_id: int = 1, # Hardcoded user ID for PoC
    db: Session = Depends(get_db)
):
    # Check if user exists (optional but good practice)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")

    # Call LLM to extract title and company
    extracted_info = await logic.extract_job_info_with_llm(job_input.description_text)

    # Prepare data for database creation
    job_data_to_create = schemas.JobCreate(
        title=extracted_info.title,             # Use extracted title
        company=extracted_info.company,         # Use extracted company
        description_text=job_input.description_text # Use original full text
    )

    # Create job in the database
    try:
        created_job = crud.create_job(db=db, job=job_data_to_create, user_id=user_id)
        return created_job
    except Exception as e:
        # Log the error appropriately
        # logger.error(f"Failed to create job after LLM extraction: {e}") # Ensure logger is configured if used
        raise HTTPException(status_code=500, detail="Failed to save job after processing.")

# --- Pydantic Models ---
class TailoringRequest(BaseModel):
    job_description: str

class TailoringResponse(BaseModel):
    suggestions: str

# --- Job Ranking and Tailoring Endpoints ---
from pydantic import BaseModel
from typing import Optional

class JobRankResponse(BaseModel):
    score: Optional[float] = None
    explanation: Optional[str] = None

@app.post("/jobs/{job_id}/rank", response_model=JobRankResponse, tags=["LLM Features"])
async def rank_job_endpoint(job_id: int, db: Session = Depends(get_db)):
    """Triggers LLM ranking for a specific job based on user 1's profile."""
    user_id = 1
    score, explanation = await logic.rank_job_with_llm(db=db, job_id=job_id, user_id=user_id)
    if score is None or explanation is None:
        raise HTTPException(status_code=500, detail="Failed to rank job using LLM")
    
    db.commit()
    
    return {"score": score, "explanation": explanation}

class ResumeTailoringRequest(BaseModel):
    job_description: str
    profile_snippet: str

class ResumeTailoringResponse(BaseModel):
    suggestions: Optional[str] = None

@app.post("/resume/suggest_tailoring", response_model=ResumeTailoringResponse, tags=["LLM Features"])
async def suggest_tailoring_endpoint(request: ResumeTailoringRequest):
    """Generates resume tailoring suggestions based on job description and profile snippet."""
    suggestions = await logic.suggest_resume_tailoring(
        job_description=request.job_description,
        profile_snippet=request.profile_snippet
    )
    if suggestions is None:
        raise HTTPException(status_code=500, detail="Failed to generate resume tailoring suggestions using LLM")
    return {"suggestions": suggestions}

# --- Autofill Mapping Endpoint ---
@app.post("/autofill/map_poc", response_model=Dict[str, str], tags=["Autofill"])
async def map_autofill_fields_poc(
    form_fields: List[schemas.FormFieldInfo],
    user_id: int = 1,  
    db: Session = Depends(get_db)
):
    """POC endpoint to map user profile data to given form fields using LLM.
    
    First checks if the user profile exists before attempting to use LLM.
    """
    profile_json_str = crud.get_user_profile(db=db, user_id=user_id)
    if profile_json_str is None:
        raise HTTPException(status_code=404, detail=f"Profile not found for user {user_id}")
        
    try:
        mapping = await logic.map_form_fields_with_llm(
            db=db,
            user_id=user_id,
            form_fields=form_fields
        )
        return mapping
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to map autofill fields: {e}")

# --- New Endpoint ---
@app.post("/users/{user_id}/jobs/tailor-suggestions", response_model=TailoringResponse)
async def get_tailoring_suggestions_endpoint(
    request_data: TailoringRequest,
    user_id: int = Path(..., title="The ID of the user to get suggestions for"),
    db: Session = Depends(get_db)
):
    """
    Generates tailoring suggestions for a given job description based on the user's profile.
    """
    db_profile = crud.get_user_profile(db, user_id=user_id)
    if db_profile is None:
        raise HTTPException(status_code=404, detail=f"User profile not found for user_id {user_id}")

    try:
        suggestions = await logic.get_tailoring_suggestions(
            profile_text=db_profile,
            job_description=request_data.job_description
        )
        return TailoringResponse(suggestions=suggestions)
    except Exception as e:
        print(f"Error generating tailoring suggestions: {e}") 
        raise HTTPException(status_code=500, detail="Failed to generate tailoring suggestions.")

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
