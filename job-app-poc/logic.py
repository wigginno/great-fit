import logging
import re
import json
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

# Project imports
from llm_interaction import call_gemini
import crud
import models
import schemas

logger = logging.getLogger(__name__)

def get_value_from_nested_dict(data_dict: Dict[str, Any], key_string: str) -> Optional[Any]:
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

    prompt = f"""Analyze the following job description and user profile snippet.
Provide a relevance score from 1 (low) to 10 (high) and a brief one-sentence explanation.

Job Description:
```
{job_description_text}
```

User Profile Snippet:
```json
{profile_snippet}
```

Respond ONLY in the format:
Score: [score]
Explanation: [explanation]"""

    llm_response = await call_gemini(prompt)

    if not llm_response:
        logger.error(f"LLM call failed for job {job_id}, user {user_id}")
        return None, None

    try:
        score_match = re.search(r"Score:\s*([\d\.]+)", llm_response)
        explanation_match = re.search(r"Explanation:\s*(.*)", llm_response, re.IGNORECASE)

        if not score_match or not explanation_match:
            logger.error(f"Could not parse LLM response for job {job_id}. Response: {llm_response}")
            return None, None

        score_str = score_match.group(1)
        explanation = explanation_match.group(1).strip()
        score = float(score_str)

        score = max(1.0, min(10.0, score))

    except (ValueError, AttributeError) as e:
        logger.error(f"Error parsing score/explanation from LLM response for job {job_id}: {e}. Response: {llm_response}")
        return None, None

    updated_job = crud.update_job_ranking(db, job_id=job_id, user_id=user_id, score=score, explanation=explanation)
    if not updated_job:
        logger.error(f"Failed to update job ranking in DB for job {job_id}")
        return None, None

    logger.info(f"Successfully ranked job {job_id} for user {user_id}. Score: {score}")
    return score, explanation

async def suggest_resume_tailoring(job_description: str, profile_snippet: str):
    logger.info("Generating resume tailoring suggestions.")
    prompt = f"""Given the following job description and a snippet from a user's profile/resume, provide 3-5 specific, actionable suggestions (as bullet points) on how to tailor the profile snippet to better match the job description.
Focus on incorporating keywords, highlighting relevant skills/experience, and using quantifiable achievements where possible.

Job Description:
```
{job_description}
```

Profile Snippet:
```
{profile_snippet}
```

Suggestions:"""

    llm_response = await call_gemini(prompt)

    if not llm_response:
        logger.error("LLM call failed for resume tailoring suggestions.")
        return None

    logger.info("Successfully generated resume tailoring suggestions.")
    return llm_response.strip() 

async def map_form_fields_with_llm(db: Session, user_id: int, form_fields: List[schemas.FormFieldInfo]) -> Dict[str, str]:
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

    llm_key_mapping = await call_gemini(prompt, expect_json=True)

    if not llm_key_mapping or not isinstance(llm_key_mapping, dict):
        logger.error(f"LLM did not return a valid JSON dictionary for field mapping. Response: {llm_key_mapping}")
        return {}

    logger.info(f"LLM returned key mapping: {llm_key_mapping}")

    final_mapping: Dict[str, str] = {}
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
    print("Generating tailoring suggestions via Gemini...") 

    prompt = f"""
    Given the following user profile/resume and job description, provide specific, actionable suggestions
    on how the user can tailor their profile/resume to better match the requirements and keywords
    in the job description. Focus on highlighting relevant skills, experiences, and keywords.
    Format the suggestions as a clear, concise list or paragraph.

    User Profile/Resume:
    ---
    {profile_text}
    ---

    Job Description:
    ---
    {job_description}
    ---

    Tailoring Suggestions:
    """

    try:
        suggestions = await call_gemini(prompt) 

        print("Successfully generated suggestions via Gemini.") 
        return suggestions

    except Exception as e:
        print(f"Error calling Gemini for tailoring suggestions: {e}")
        raise Exception(f"LLM (Gemini) API call failed: {e}")

def _summarize_profile(profile_data: Dict[str, Any]) -> str:
    return json.dumps(profile_data)

async def extract_job_info_with_llm(description_text: str) -> schemas.ExtractedJobInfo:
    """
    Uses an LLM to extract the job title and company from raw description text.

    Args:
        description_text: The raw job description text.

    Returns:
        A Pydantic model containing the extracted title and company,
        or default values if extraction fails.
    """
    prompt = f"""
Analyze the following job description text and extract the job title and the company name.
Return the result strictly as a JSON object with the keys "title" and "company".
- The "title" should be the most appropriate job title found.
- The "company" should be the name of the hiring company.
If you cannot definitively identify a title or company, use "Unknown Title" or "Unknown Company" respectively.

Job Description Text:
---
{description_text[:2000]} # Limit input length for safety/cost
---

JSON Output:
"""
    default_info = schemas.ExtractedJobInfo(title="Unknown Title", company="Unknown Company")

    try:
        logger.info("Attempting to extract job info with LLM...")
        # call_gemini with expect_json=True should return a dict directly
        llm_response_dict = await call_gemini(prompt, expect_json=True)

        if not llm_response_dict or not isinstance(llm_response_dict, dict):
            logger.warning(f"LLM returned unexpected response for job info extraction: {llm_response_dict}")
            return default_info

        # Use the dictionary directly (no json.loads needed)
        # Pydantic will raise validation error if keys are missing or types are wrong
        extracted_info = schemas.ExtractedJobInfo(**llm_response_dict)
        logger.info(f"Successfully extracted job info: {extracted_info}")
        return extracted_info

    except Exception as e: # Catch Pydantic validation errors or other unexpected issues
        logger.error(f"Error processing LLM response for job info extraction: {e}")
        return default_info
