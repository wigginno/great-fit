import hashlib
import functools
import structlog
from sqlalchemy.orm import Session
from typing import Any, Union
import fastapi
import schemas
import models
import json

# Project imports
from llm_interaction import (
    call_llm_for_job_ranking,
    call_llm_for_resume_tailoring,
    call_llm_for_resume_parsing,
    call_llm_to_clean_job_description,
)
import crud

# Set up logging
logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------

async def parse_job_description_with_llm(raw_description: str) -> schemas.CleanedJobDescription:
    """
    Extract `title`, `company`, and `description` from an unstructured job posting.

    Returns
    -------
    schemas.CleanedJobDescription  • An object containing title, company, and cleaned_markdown.
    Raises
    ------
    fastapi.HTTPException      • if any required field is missing
    """
    # Clean job description using LLM parse endpoint
    cleaned = await call_llm_to_clean_job_description_cached(raw_description)
    if not cleaned or not (cleaned.title and cleaned.company and cleaned.cleaned_markdown):
        raise fastapi.HTTPException(
            status_code=422,
            detail="Failed to extract required fields (title, company, description) from job description."
        )
    return cleaned

# Simple LLM response cache to reduce API calls
_LLM_CACHE = {}


def cache_llm_response(func):
    """Decorator to cache LLM responses based on function parameters"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Create a unique key based on function name and all arguments
        # Convert all args to strings for hashing
        args_str = [str(arg) for arg in args]
        kwargs_str = [f"{k}={v}" for k, v in sorted(kwargs.items())]
        all_args = func.__name__ + "|" + "|".join(args_str + kwargs_str)
        cache_key = hashlib.md5(all_args.encode()).hexdigest()

        # Check if we have a cached response
        if cache_key in _LLM_CACHE:
            logger.info(
                f"Using cached LLM response for {func.__name__}, hash {cache_key[:8]}"
            )
            return _LLM_CACHE[cache_key]

        # Call the LLM function
        result = await func(*args, **kwargs)

        # Cache the result
        if result is not None:
            _LLM_CACHE[cache_key] = result

        return result

    return wrapper


# Apply caching to all LLM functions
call_llm_for_job_ranking_cached = cache_llm_response(call_llm_for_job_ranking)
call_llm_for_resume_tailoring_cached = cache_llm_response(call_llm_for_resume_tailoring)
call_llm_for_resume_parsing_cached = cache_llm_response(call_llm_for_resume_parsing)
call_llm_to_clean_job_description_cached = cache_llm_response(
    call_llm_to_clean_job_description
)


async def clean_job_description(
    raw_markdown: str,
) -> Union[schemas.CleanedJobDescription, None]:
    """Cleans job description markdown using a cached LLM call."""
    logger.info("Attempting to clean job description using cached LLM call.")
    cleaned_data = await call_llm_to_clean_job_description_cached(raw_markdown)
    return cleaned_data


async def rank_job_with_llm(db: Session, job_id: int, user_id: int):
    logger.info("Ranking job", job_id=job_id, user_id=user_id)

    db_job = crud.get_job(db, job_id=job_id, user_id=user_id)
    if not db_job:
        logger.error("Job not found for user", job_id=job_id, user_id=user_id)
        return None, None

    profile_json_string = crud.get_user_profile(db, user_id=user_id)
    job_description_text = db_job.description

    result = await call_llm_for_job_ranking_cached(
        job_description_text, profile_json_string
    )
    score = result.score
    explanation = result.explanation

    updated_job = crud.update_job_ranking(
        db, job_id=job_id, user_id=user_id, score=score, explanation=explanation
    )
    if not updated_job:
        logger.error("Failed to update job ranking in DB", job_id=job_id)
        return None, None

    logger.info("Successfully ranked job", job_id=job_id, user_id=user_id, score=score)
    return score, explanation


# Resume parsing function using a single LLM call for structured output
async def parse_resume_with_llm(resume_text: str) -> dict[str, Any]:
    """
    Uses LLM to parse a resume text and extract all structured information in a single call.
    Takes advantage of structured JSON output for consistency and reliability.

    Args:
        resume_text: The raw text extracted from the uploaded resume.

    Returns:
        A dictionary containing structured profile data extracted from the resume.
    """
    parsed_data = await call_llm_for_resume_parsing(resume_text)
    return parsed_data.model_dump()


async def generate_tailoring_suggestions(job: models.Job, db: Session) -> Union[str, None]:
    """Fetches user profile and generates tailoring suggestions for a given job."""
    if not job.owner_id:
        print(f"Error: Job {job.id} has no associated owner_id.")
        return None

    profile_json_string = crud.get_user_profile(db, user_id=job.owner_id)

    # Parse the profile JSON string and extract profile text
    profile_data = json.loads(profile_json_string)
    profile_text = json.dumps(profile_data, indent=2)

    # Include ranking explanation if available to provide additional context
    ranking_context = ""
    if job.ranking_explanation:
        ranking_context = (
            f"\n\nAnalysis of Profile Match to Job:\n{job.ranking_explanation}"
        )

    response: schemas.TailoringResponse = await call_llm_for_resume_tailoring_cached(
        job_description=job.description,
        applicant_profile=profile_text + ranking_context,
    )
    suggestions_text = "\n".join([f"- {s}" for s in response.suggestions])
    return suggestions_text
