import json
import hashlib
import functools
import logging
from sqlalchemy.orm import Session
from typing import Any, Optional

# For structured output models
from pydantic import Field

# Project imports
from llm_interaction import call_llm_for_resume_parsing, call_llm_for_job_ranking, call_llm_for_resume_tailoring
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
            logger.info(f"Using cached LLM response for {func.__name__}, hash {cache_key[:8]}")
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

def get_value_from_nested_dict(data_dict: dict[str, Any], key_string: str) -> Optional[Any]:
    keys = key_string.split('.')
    value = data_dict
    try:
        for key in keys:
            if isinstance(value, list):
                try:
                    index = int(key)
                    if 0 <= index < len(value):
                        value = value[index]
                    else:
                        logger.debug(f"Index {index} out of bounds for key '{key_string}'")
                        return None 
                except ValueError:
                    logger.debug(f"Key '{key}' is not a valid list index for key '{key_string}'")
                    return None 
            elif isinstance(value, dict):
                value = value[key]
            else:
                logger.debug(f"Cannot traverse further at key '{key}' for key '{key_string}'")
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
        logger.warning(f"User profile not found for user {user_id}. Ranking based on job only.")
        profile_snippet = "User profile not available."
    else:
        try:
            profile_data = json.loads(profile_json_string)
            profile_snippet = json.dumps({
                "summary": profile_data.get("summary", "N/A"),
                "skills": profile_data.get("skills", [])[:5], 
            })
        except json.JSONDecodeError:
             logger.error(f"Failed to parse profile JSON for user {user_id}")
             profile_snippet = "Error parsing profile."
        except Exception as e:
             logger.error(f"Error processing profile for user {user_id}: {e}")
             profile_snippet = "Error processing profile."

    job_description_text = db_job.description_text

    try:
        # Use the new structured job ranking function
        result = await call_llm_for_job_ranking_cached(job_description_text, profile_snippet)

        # Extract score and explanation from the structured result
        score = result.score
        explanation = result.explanation

        # Ensure score is within bounds
        score = max(1.0, min(10.0, score))        
    except Exception as e:
        logger.error(f"Error calling LLM for job ranking for job {job_id}, user {user_id}: {e}")
        return None, None

    updated_job = crud.update_job_ranking(db, job_id=job_id, user_id=user_id, score=score, explanation=explanation)
    if not updated_job:
        logger.error(f"Failed to update job ranking in DB for job {job_id}")
        return None, None

    logger.info(f"Successfully ranked job {job_id} for user {user_id}. Score: {score}")
    return score, explanation

async def suggest_resume_tailoring(job_description: str, profile_snippet: str):
    logger.info("Generating resume tailoring suggestions.")

    try:
        # Use the new structured tailoring suggestions function
        suggestions = await call_llm_for_resume_tailoring_cached(job_description, profile_snippet)

        # Format suggestions as a string
        formatted_suggestions = "\n".join([f"- {suggestion}" for suggestion in suggestions.suggestions])

        logger.info("Successfully generated resume tailoring suggestions.")
        return formatted_suggestions.strip()
    except Exception as e:
        logger.error(f"LLM call failed for resume tailoring suggestions: {e}")
        return None

async def map_form_fields_with_llm(db: Session, user_id: int, form_fields: list[schemas.FormFieldInfo]) -> dict[str, str]:
    """This is a placeholder/toy function until I get around to doing it properly."""
    logger.info(f"Mapping form fields for user {user_id}")

    profile_json_string = crud.get_user_profile(db, user_id=user_id)
    if not profile_json_string:
        logger.error(f"User profile not found for user {user_id}. Cannot perform mapping.")
        return {}

    try:
        user_profile_dict = json.loads(profile_json_string)
        if 'profile_data' in user_profile_dict and isinstance(user_profile_dict['profile_data'], dict):
            user_profile_dict = user_profile_dict['profile_data']
        logger.debug(f"User profile data for mapping: {user_profile_dict}")
    except json.JSONDecodeError:
        logger.error(f"Failed to parse profile JSON for user {user_id}. Cannot perform mapping.")
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
        logger.error(f"LLM did not return a valid JSON dictionary for field mapping. Response: {llm_key_mapping}")
        return {}

    logger.info(f"LLM returned key mapping: {llm_key_mapping}")

    final_mapping: dict[str, str] = {}
    for field_id, profile_key in llm_key_mapping.items():
        if not isinstance(profile_key, str):
            logger.warning(f"LLM returned non-string key '{profile_key}' for field '{field_id}'. Skipping.")
            continue

        actual_value = get_value_from_nested_dict(user_profile_dict, profile_key)

        if actual_value is not None:
            final_mapping[field_id] = str(actual_value)
            logger.debug(f"Mapped field '{field_id}' -> key '{profile_key}' -> value '{str(actual_value)}'")
        else:
            logger.warning(f"LLM mapped field '{field_id}' to key '{profile_key}', but value not found/accessible in profile.")

    logger.info(f"Final autofill mapping generated: {final_mapping}")
    return final_mapping

async def get_tailoring_suggestions(profile_text: str, job_description: str) -> str:
    logger.info("Generating tailoring suggestions...") 

    try:
        # Call the new structured tailoring suggestions function
        suggestions = await call_llm_for_resume_tailoring_cached(job_description, profile_text)

        # Format suggestions as a string if they're returned as a list
        if isinstance(suggestions, list):
            formatted_suggestions = "\n".join([f"- {suggestion}" for suggestion in suggestions])
        else:
            formatted_suggestions = suggestions

        logger.info("Successfully generated tailoring suggestions.") 
        return formatted_suggestions

    except Exception as e:
        logger.error(f"Error calling LLM for tailoring suggestions: {e}")
        raise Exception(f"LLM API call failed: {e}")

def _summarize_profile(profile_data: dict[str, Any]) -> str:
    return json.dumps(profile_data)

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

        # Process sections to extract education, experience, and other information
        education = []
        experience = []
        projects = []
        summary = ""

        # Process all sections from the parsed data
        logger.info(f"Processing {len(parsed_data.sections)} sections from parsed resume")
        sections = parsed_data.sections
        for section in sections:
            section_title = section.title.lower()
            logger.info(f"Processing section: '{section.title}'")

            # Extract education information
            if "education" in section_title:
                logger.info(f"Found education section with {len(section.subsections)} subsections")
                # Log detailed structure of education section
                for i, subsection in enumerate(section.subsections):
                    logger.info(f"Education subsection {i+1}: title='{subsection.title}', entries={len(subsection.entries)}")
                    for j, entry in enumerate(subsection.entries):
                        logger.info(f"  - Entry {j+1}: '{entry}'")
                    edu_item = {
                        "institution": subsection.title,
                        "details": subsection.entries
                    }
                    education.append(edu_item)
                # If no subsections, try to extract from entries directly
                if len(section.subsections) == 0 and len(section.entries) > 0:
                    logger.info(f"Education section has no subsections but {len(section.entries)} direct entries")
                    for entry in section.entries:
                        logger.info(f"Direct education entry: '{entry}'")
                        # Try to extract institution from entry
                        parts = entry.split(' - ', 1)
                        if len(parts) > 1:
                            institution = parts[0].strip()
                            details = [parts[1].strip()]
                        else:
                            institution = "Unknown Institution"
                            details = [entry]
                        edu_item = {
                            "institution": institution,
                            "details": details
                        }
                        education.append(edu_item)

            # Extract experience information
            elif "experience" in section_title or "employment" in section_title:
                for subsection in section.subsections:
                    title_parts = subsection.title.split("-", 1)
                    company = title_parts[0].strip() if len(title_parts) > 0 else ""
                    position = title_parts[1].strip() if len(title_parts) > 1 else ""

                    exp_item = {
                        "company": company,
                        "position": position,
                        "description": subsection.entries
                    }
                    experience.append(exp_item)

            # Extract projects information
            elif "project" in section_title:
                for subsection in section.subsections:
                    project_item = {
                        "name": subsection.title,
                        "description": subsection.entries
                    }
                    projects.append(project_item)

            # Extract summary information
            elif "summary" in section_title or "objective" in section_title:
                summary = "\n".join(section.entries)

        # Add processed sections to resume_data
        resume_data["education"] = education
        resume_data["experience"] = experience

        # Add optional sections if available
        if projects:
            resume_data["projects"] = projects
        if summary:
            resume_data["summary"] = summary

        logger.info("Resume successfully parsed in a single LLM call")
        return resume_data

    except Exception as e:
        logger.error(f"Error parsing resume with LLM: {e}")
        # Create a fallback structure with minimal data
        return {
            "skills": [],
            "education": [],
            "experience": []
        }
