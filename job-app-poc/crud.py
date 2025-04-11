import json
from sqlalchemy.orm import Session

import models
import schemas

# --- User CRUD ---
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate):
    # In a real app, hash the password here
    db_user = models.User(email=user.email)
    db.add(db_user)
    db.flush() # Assign ID without committing
    db.refresh(db_user)
    return db_user

# --- User Profile CRUD ---
def get_user_profile(db: Session, user_id: int):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        return user.profile_json # Returns the raw JSON string
    return None

def create_or_update_user_profile(db: Session, user_id: int, profile: schemas.UserProfileCreate):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None # Or raise HTTPException in the endpoint

    profile_json_string = json.dumps(profile.profile_data)
    user.profile_json = profile_json_string
    db.add(user) # add works for updates too
    db.flush() # Ensure changes are sent before refresh
    db.refresh(user)
    # Return the stored JSON string, endpoint will handle parsing for response model
    return user.profile_json

# --- Job CRUD ---
def create_job(db: Session, job: schemas.JobCreate, user_id: int):
    db_job = models.Job(**job.model_dump(), user_id=user_id)
    db.add(db_job)
    db.commit() # Explicitly commit the transaction
    db.flush()
    db.refresh(db_job)
    return db_job

def get_jobs_for_user(db: Session, user_id: int):
    return db.query(models.Job).filter(models.Job.user_id == user_id).all()

def get_job(db: Session, job_id: int, user_id: int):
    return db.query(models.Job).filter(models.Job.id == job_id, models.Job.user_id == user_id).first()

def update_job_ranking(db: Session, job_id: int, user_id: int, score: float, explanation: str):
    db_job = db.query(models.Job).filter(models.Job.id == job_id, models.Job.user_id == user_id).first()
    if not db_job:
        return None # Or raise HTTPException in the endpoint

    db_job.ranking_score = score
    db_job.ranking_explanation = explanation
    db.add(db_job)
    db.flush()
    db.refresh(db_job)
    return db_job
