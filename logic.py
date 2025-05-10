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
from llm_interaction import call_llm, MODEL_CONFIG
import crud

# Set up logging
logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
import asyncio

async def parse_job_description_with_llm(raw_description: str) -> dict[str, str]:
    """
    Extract `title`, `company`, and `description` from an unstructured job posting.

    Returns
    -------
    dict[str, str]  • keys: title, company, description
    Raises
    ------
    ValueError      • if any required field is missing
    """
    system_prompt = (
        "You are a strictly-formatted information extractor. "
        "Read the following job posting and return **only** JSON with exactly three "
        "string properties: `title`, `company`, `description`. "
        "Do not add, rename, omit, or nest keys. Preserve description paragraphs."
    )
    user_prompt = f"{raw_description}"
    # Clean job description using LLM parse endpoint
    cleaned = await call_llm_to_clean_job_description_cached(raw_description)
    if not cleaned or not (cleaned.title and cleaned.company and cleaned.cleaned_markdown):
        raise fastapi.HTTPException(
            status_code=422,
            detail="Failed to extract required fields (title, company, description) from job description."
        )
    return {
        "title": cleaned.title,
        "company": cleaned.company,
        "description": cleaned.cleaned_markdown,
    }

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
    parsed_data = await call_llm_for_resume_parsing(
        resume_text
    )  # Call the renamed function

    # Map the new structure to the expected structure
    resume_data = {}

    # Extract skills
    resume_data["skills"] = parsed_data.skills

    # Convert sections from the LLM response to a dictionary format
    resume_data["sections"] = []

    # Process each section and convert to dictionary
    for section in parsed_data.sections:
        section_dict = {
            "title": section.title,
            "entries": section.entries,
            "subsections": [],
        }

        # Convert subsections to dictionary format
        for subsection in section.subsections:
            section_dict["subsections"].append(
                {"title": subsection.title, "entries": subsection.entries}
            )

        # Add the processed section to resume_data
        resume_data["sections"].append(section_dict)

    return resume_data


async def process_resume_upload(resume: fastapi.UploadFile) -> dict:
    """Process uploaded resume file, parse content, and return structured data."""
    file_content = await resume.read()
    resume_text = parse_document(resume.filename, file_content)
    parsed_data = await parse_resume_with_llm(resume_text)
    return parsed_data.model_dump() if parsed_data else {}


async def generate_tailoring_suggestions(job: models.Job, db: Session) -> Union[str, None]:
    """Fetches user profile and generates tailoring suggestions for a given job."""
    if not job.user_id:
        print(f"Error: Job {job.id} has no associated user_id.")
        return None

    profile_json_string = crud.get_user_profile(db, user_id=job.user_id)
    if not profile_json_string:
        print(
            f"Warning: Profile not found for user {job.user_id}. Cannot generate tailoring suggestions."
        )
        return None

    # Parse the profile JSON string
    try:
        profile_data = json.loads(profile_json_string)
    except json.JSONDecodeError:
        print(f"Error: Invalid profile JSON for user {job.user_id}")
        return None

    if not job.description:
        print(
            f"Warning: Job {job.id} has no description. Cannot generate tailoring suggestions."
        )
        return None

    # Extract profile text from the JSON data
    profile_text = json.dumps(
        profile_data, indent=2
    )  # Convert to formatted text for LLM

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

    if response and response.suggestions:
        suggestions_text = "\n".join([f"- {s}" for s in response.suggestions])
        return suggestions_text
    else:
        print(f"No tailoring suggestions received from LLM for job {job.id}.")
        return None
