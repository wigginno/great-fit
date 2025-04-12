import json
import hashlib
import functools
import re
import logging
from sqlalchemy.orm import Session
from typing import Any, Optional

# Project imports
from llm_interaction import (
    call_llm_for_resume_parsing,
    call_llm_for_job_ranking,
    call_llm_for_resume_tailoring,
)
import crud
import schemas

# Set up logging
logger = logging.getLogger(__name__)

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
call_llm_for_resume_parsing_cached = cache_llm_response(call_llm_for_resume_parsing)
call_llm_for_job_ranking_cached = cache_llm_response(call_llm_for_job_ranking)
call_llm_for_resume_tailoring_cached = cache_llm_response(call_llm_for_resume_tailoring)


def get_value_from_nested_dict(
    data_dict: dict[str, Any], key_string: str
) -> Optional[Any]:
    keys = key_string.split(".")
    value = data_dict
    try:
        for key in keys:
            if isinstance(value, list):
                try:
                    index = int(key)
                    if 0 <= index < len(value):
                        value = value[index]
                    else:
                        logger.debug(
                            f"Index {index} out of bounds for key '{key_string}'"
                        )
                        return None
                except ValueError:
                    logger.debug(
                        f"Key '{key}' is not a valid list index for key '{key_string}'"
                    )
                    return None
            elif isinstance(value, dict):
                value = value[key]
            else:
                logger.debug(
                    f"Cannot traverse further at key '{key}' for key '{key_string}'"
                )
                return None
        return value
    except (KeyError, TypeError, IndexError) as e:
        logger.debug(f"Error accessing key '{key_string}': {e}")
        return None


async def rank_job_with_llm(db: Session, job_id: int, user_id: int):
    logger.info(f"Ranking job {job_id} for user {user_id}")

    db_job = crud.get_job(db, job_id=job_id, user_id=user_id)
    if not db_job:
        logger.error(f"Job {job_id} not found for user {user_id}")
        return None, None

    profile_json_string = crud.get_user_profile(db, user_id=user_id)
    if not profile_json_string:
        logger.warning(
            f"User profile not found for user {user_id}. Ranking based on job only."
        )
        profile_snippet = "User profile not available."
    else:
        try:
            profile_data = json.loads(profile_json_string)
            profile_snippet = json.dumps(
                {
                    "skills": profile_data.get("skills", [])[:5],
                }
            )
        except json.JSONDecodeError:
            logger.error(f"Failed to parse profile JSON for user {user_id}")
            profile_snippet = "Error parsing profile."
        except Exception as e:
            logger.error(f"Error processing profile for user {user_id}: {e}")
            profile_snippet = "Error processing profile."

    job_description_text = db_job.description

    try:
        # Use the new structured job ranking function
        result = await call_llm_for_job_ranking_cached(
            job_description_text, profile_snippet
        )

        # Extract score and explanation from the structured result
        score = result.score
        explanation = result.explanation

        # Ensure score is within bounds
        score = max(1.0, min(10.0, score))
    except Exception as e:
        logger.error(
            f"Error calling LLM for job ranking for job {job_id}, user {user_id}: {e}"
        )
        return None, None

    updated_job = crud.update_job_ranking(
        db, job_id=job_id, user_id=user_id, score=score, explanation=explanation
    )
    if not updated_job:
        logger.error(f"Failed to update job ranking in DB for job {job_id}")
        return None, None

    logger.info(f"Successfully ranked job {job_id} for user {user_id}. Score: {score}")
    return score, explanation


async def suggest_resume_tailoring(job_description: str, profile_snippet: str):
    logger.info("Generating resume tailoring suggestions.")

    try:
        # Use the new structured tailoring suggestions function
        suggestions = await call_llm_for_resume_tailoring_cached(
            job_description, profile_snippet
        )

        # Format suggestions as a string
        formatted_suggestions = "\n".join(
            [suggestion for suggestion in suggestions.suggestions]
        )

        logger.info("Successfully generated resume tailoring suggestions.")
        return formatted_suggestions.strip()
    except Exception as e:
        logger.error(f"LLM call failed for resume tailoring suggestions: {e}")
        return None


async def map_form_fields_with_llm(
    db: Session, user_id: int, form_fields: list[schemas.FormFieldInfo]
) -> dict[str, str]:
    """This is a placeholder/toy function until I get around to doing it properly."""
    logger.info(f"Mapping form fields for user {user_id}")

    profile_json_string = crud.get_user_profile(db, user_id=user_id)
    if not profile_json_string:
        logger.error(
            f"User profile not found for user {user_id}. Cannot perform mapping."
        )
        return {}

    try:
        user_profile_dict = json.loads(profile_json_string)
        if "profile_data" in user_profile_dict and isinstance(
            user_profile_dict["profile_data"], dict
        ):
            user_profile_dict = user_profile_dict["profile_data"]
        logger.debug(f"User profile data for mapping: {user_profile_dict}")
    except json.JSONDecodeError:
        logger.error(
            f"Failed to parse profile JSON for user {user_id}. Cannot perform mapping."
        )
        return {}

    form_fields_list = [field.model_dump(exclude_none=True) for field in form_fields]
    try:
        form_fields_json = json.dumps(form_fields_list, indent=2)
    except TypeError:
        logger.error("Failed to serialize form fields to JSON.")
        return {}

    prompt = f"""You are an expert form-filling assistant. Analyze the provided web form fields and user profile data. Map the user data to the appropriate form fields based on semantic meaning (labels, names, types, placeholders).

User Profile Data:
```json
{json.dumps(user_profile_dict, indent=2)}
```

Form Fields:
```json
{form_fields_json}
```

Task: Return a JSON object mapping the `field_id` from the Form Fields list to the corresponding **full path key** from the User Profile Data JSON (e.g., 'contact.firstName', 'experience.0.company', 'skills.2'). If a form field cannot be confidently mapped to a specific profile key, omit its `field_id` from the result JSON object. Respond ONLY with the JSON mapping object.

Example Response Format:
{{'field_id_for_firstname': 'contact.firstName', 'field_id_for_email': 'contact.email', 'field_id_for_company': 'experience.0.company'}}
"""

    llm_key_mapping = await call_llm_cached(prompt, expect_json=True)

    if not llm_key_mapping or not isinstance(llm_key_mapping, dict):
        logger.error(
            f"LLM did not return a valid JSON dictionary for field mapping. Response: {llm_key_mapping}"
        )
        return {}

    logger.info(f"LLM returned key mapping: {llm_key_mapping}")

    final_mapping: dict[str, str] = {}
    for field_id, profile_key in llm_key_mapping.items():
        if not isinstance(profile_key, str):
            logger.warning(
                f"LLM returned non-string key '{profile_key}' for field '{field_id}'. Skipping."
            )
            continue

        actual_value = get_value_from_nested_dict(user_profile_dict, profile_key)

        if actual_value is not None:
            final_mapping[field_id] = str(actual_value)
            logger.debug(
                f"Mapped field '{field_id}' -> key '{profile_key}' -> value '{str(actual_value)}'"
            )
        else:
            logger.warning(
                f"LLM mapped field '{field_id}' to key '{profile_key}', but value not found/accessible in profile."
            )

    logger.info(f"Final autofill mapping generated: {final_mapping}")
    return final_mapping


async def get_tailoring_suggestions(profile_text: str, job_description: str) -> str:
    logger.info("Generating tailoring suggestions...")

    try:
        # Call the new structured tailoring suggestions function
        response = await call_llm_for_resume_tailoring_cached(
            job_description, profile_text
        )

        # Extract suggestions from TailoringSuggestions object
        if hasattr(response, "suggestions"):
            suggestions = response.suggestions
        else:
            # Handle case where response might be the direct value
            suggestions = response

        # Format suggestions as a string if they're returned as a list
        if isinstance(suggestions, list):
            formatted_suggestions = "\n".join(
                [suggestion for suggestion in suggestions]
            )
        else:
            formatted_suggestions = str(suggestions)

        logger.info("Successfully generated tailoring suggestions.")
        return formatted_suggestions

    except Exception as e:
        logger.error(f"Error calling LLM for tailoring suggestions: {e}")
        raise Exception(f"LLM API call failed: {e}")


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
    try:
        # Use the new structured resume parsing function
        parsed_data = await call_llm_for_resume_parsing_cached(resume_text)

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

    except Exception as e:
        logger.error(f"Error parsing resume with LLM: {e}")
        # Create a fallback structure with minimal data
        return {"skills": [], "sections": []}


# Job description formatter using LLM
async def format_job_details_with_llm(job_description: str) -> dict:
    """
    Format and clean up a job description text using LLM.
    Retains all important information but cleans up formatting quirks.

    Args:
        job_description: Raw job description text pasted from a job site

    Returns:
        Dictionary with cleaned up job description
    """
    try:
        # Define the prompt for formatting the job description and extracting key information
        prompt = f"""Please extract key information and clean up the formatting of this job description text.

        1. First, extract these key pieces of information:
           - Job Title: What is the exact title of the position?
           - Company Name: What company posted this job?

        2. Then clean up the formatting of the full description:
           - Remove extraneous header/footer text unrelated to the job posting
           - Fix inconsistent spacing and line breaks
           - Properly format bullet points 
           - Fix weird character encodings
           - Format sections with clear headings
           - Remove UI artifacts like 'Click to apply', 'Show more', etc.
           - Remove social media buttons and other non-content elements

        Do NOT summarize or paraphrase the content. Keep ALL the original information intact.

        Here is the job description to clean up:

        {job_description}

        Your response should start with the extracted job title and company, followed by the full formatted description:
        TITLE: [Extracted Job Title]
        COMPANY: [Extracted Company Name]
        DESCRIPTION: [Full formatted job description]
        """

        # Set up a simple request to the LLM
        import openai
        from openai import OpenAI
        import os

        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are a job description formatter. You clean up raw job descriptions to make them more readable without losing any information.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,  # Lower temperature for more consistent formatting
            max_tokens=2000,
        )

        formatted_response = response.choices[0].message.content.strip()

        # Extract the title, company, and description from the formatted response
        job_title = "New Job"  # Default fallback
        company_name = "Unknown Company"  # Default fallback
        description_text = formatted_response  # Full text as fallback

        # Try to parse the structured response
        try:
            # Look for the TITLE/COMPANY/DESCRIPTION markers
            if (
                "TITLE:" in formatted_response
                and "COMPANY:" in formatted_response
                and "DESCRIPTION:" in formatted_response
            ):
                # Extract title
                title_match = re.search(r"TITLE:\s*(.+?)(?:\n|$)", formatted_response)
                if title_match:
                    job_title = title_match.group(1).strip()

                # Extract company
                company_match = re.search(
                    r"COMPANY:\s*(.+?)(?:\n|$)", formatted_response
                )
                if company_match:
                    company_name = company_match.group(1).strip()

                # Extract description
                desc_match = re.search(
                    r"DESCRIPTION:\s*(.+)", formatted_response, re.DOTALL
                )
                if desc_match:
                    description_text = desc_match.group(1).strip()
            else:
                # If no structured format found, try to extract from the first few lines
                lines = formatted_response.split("\n")
                if len(lines) > 2:
                    if not job_title or job_title == "New Job":
                        job_title = lines[0].strip()
                    if not company_name or company_name == "Unknown Company":
                        for line in lines[1:3]:  # Check the next few lines for company
                            if (
                                len(line.strip()) > 0 and len(line.strip()) < 50
                            ):  # Company names are usually short
                                company_name = line.strip()
                                break
        except Exception as e:
            logger.error(f"Error extracting job details: {e}")
            # Continue with defaults if extraction fails

        return {
            "title": job_title,
            "company": company_name,
            "description": description_text,
        }
    except Exception as e:
        logger.error(f"Error formatting job with LLM: {e}")
        # Fall back to the original text if there's an error
        return {"description": job_description}


# Function to extract job title and company from description
async def extract_job_info_with_llm(job_description: str) -> schemas.ExtractedJobInfo:
    """
    Extract job title and company name from a job description.

    Args:
        job_description: Raw job description text

    Returns:
        ExtractedJobInfo with title and company name
    """
    try:
        # For now, return placeholder values
        # In a real implementation, you'd call the LLM here to extract this information
        return schemas.ExtractedJobInfo(title="Job Position", company="Company Name")
    except Exception as e:
        logger.error(f"Error extracting job info with LLM: {e}")
        return schemas.ExtractedJobInfo(title="Job Position", company="Company Name")
