import json
from sqlalchemy.orm import Session

import models
import schemas


# --- User CRUD ---
def get_user_by_id(db: Session, user_id: int):
    """Get a user by their primary key ID."""
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


import uuid

def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(
        email=user.email,
        cognito_sub=user.cognito_sub or f"local-{uuid.uuid4()}",
        credits=10,
        profile_json=None,
    )
    db.add(db_user)
    db.flush()  # Assign ID without committing
    db.refresh(db_user)
    return db_user


# --- User Profile CRUD ---
def get_user_profile(db: Session, user_id: int):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        return user.profile_json  # Returns the raw JSON string
    return None


def create_or_update_user_profile(
    db: Session, user_id: int, profile: schemas.UserProfileCreate
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None

    profile_json_string = json.dumps(profile.profile_data)
    user.profile_json = profile_json_string
    db.add(user)  # add works for updates too
    db.commit()  # Explicitly commit the transaction to ensure it's saved to the database
    db.refresh(user)
    # Return the stored JSON string, endpoint will handle parsing for response model
    return user.profile_json


# --- Job CRUD ---
def create_job(db: Session, job: schemas.JobCreate, user_id: int):
    """Creates a new job entry associated with a user, using ranking_score and ranking_explanation only."""
    db_job = models.Job(
        owner_id=user_id,
        title=job.title,
        company=job.company,
        description=job.description,
        tailoring_suggestions=getattr(job, "tailoring_suggestions", None),
        ranking_score=getattr(job, "ranking_score", None),
        ranking_explanation=getattr(job, "ranking_explanation", None),
    )
    db.add(db_job)
    db.flush()
    return db_job


def get_jobs_for_user(db: Session, user_id: int):
    """Retrieves all jobs for a specific user."""
    return db.query(models.Job).filter(models.Job.owner_id == user_id).order_by(models.Job.created_at.desc()).all()


def get_job(db: Session, job_id: int, user_id: int):
    return (
        db.query(models.Job)
        .filter(models.Job.id == job_id, models.Job.owner_id == user_id)
        .first()
    )


def update_job_ranking(
    db: Session, job_id: int, user_id: int, score: float, explanation: str
):
    db_job = (
        db.query(models.Job)
        .filter(models.Job.id == job_id, models.Job.owner_id == user_id)
        .first()
    )
    if not db_job:
        return None  # Or raise HTTPException in the endpoint

    db_job.ranking_score = score
    db_job.ranking_explanation = explanation
    db.add(db_job)
    # db.refresh(db_job) # REMOVED - Caller should refresh after commit if needed
    return db_job


def delete_job(db: Session, job_id: int, user_id: int):
    """Delete a job for a specific user"""
    # Find the job for this user
    db_job = (
        db.query(models.Job)
        .filter(models.Job.id == job_id, models.Job.owner_id == user_id)
        .first()
    )
    if not db_job:
        return False  # Job not found or doesn't belong to this user

    # Delete the job
    db.delete(db_job)
    db.commit() # Commit the deletion
    return True
