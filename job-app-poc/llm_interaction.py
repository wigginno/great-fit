import os
import re
import logging

from openai import OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv
import instructor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# --- Configure OpenRouter API ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    logger.error("OPENROUTER_API_KEY not found in environment variables.")
    raise ValueError("OPENROUTER_API_KEY not found in environment variables. Ensure it's set in your .env file.")

# --- Application Info for OpenRouter ---
APP_NAME = "Job Application Helper"
APP_URL = "https://github.com/wigginno/job-app-helper"

# --- Initialize OpenAI client to use OpenRouter ---
client = instructor.from_openai(OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": APP_URL,
        "X-Title": APP_NAME,
    }
))

EXTRA_BODY_PARAMS = {
    "provider": {
        "order": ["Groq"],
    }
}

# --- Model Configuration ---
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"

# --- Structured Output Examples ---
PARSED_RESUME_OUTPUT_EXAMPLE = """{
    \"Sections\": [
        {
            \"title\": \"Education\",
            \"subsections\": [
                {
                    \"title\": \"University of Florida\",
                    \"entries\": [
                        \"Bachelor of Science in Computer Science\"
                    ]
                }
            ],
            \"entries\": []
        },
        {
            \"title\": \"Experience\",
            \"subsections\": [
                {
                    \"title\": \"Bob's Company - Data Engineer\",
                    \"entries\": [
                        \"Architected a data pipeline for real-time analytics improving team productivity by 20%\",
                        \"Led a team of 5 engineers in the development of a new data platform\",
                        \"Developed a custom reporting tool for sales analytics\"
                    ]
                }
            ],
            \"entries\": []
        },
        {
            \"title\": \"Certifications\",
            \"subsections\": [],
            \"entries\": [
                \"Cisco Certified Network Associate (CCNA)\",
                \"Oracle Certified Professional, Java SE 11 Developer\"
            ]
        }
    ],
    \"skills\": [
        \"FastAPI\",
        \"Django\",
        \"Python\",
        \"SQL\",
        \"Git\"
    ]
}"""
PARSED_RESUME_OUTPUT_EXAMPLE = re.sub(r"\n +", "", PARSED_RESUME_OUTPUT_EXAMPLE).replace("\n", "")

# Pydantic models
class Subsection(BaseModel):
    title: str
    entries: list[str]

class Section(BaseModel):
    title: str
    subsections: list[Subsection]
    entries: list[str]

class ResumeData(BaseModel):
    sections: list[Section]
    skills: list[str]

class JobRanking(BaseModel):
    score: float
    explanation: str

class TailoringSuggestions(BaseModel):
    suggestions: list[str]

async def call_llm_for_resume_parsing(resume_text: str) -> ResumeData:
    """Call LLM for structured resume parsing."""

    system_prompt = f"""You are a resume parser. Your task is to extract structured information from the provided resume text.
Example output: {PARSED_RESUME_OUTPUT_EXAMPLE}
Major sections may vary based on the resume, as will the subsections, bullets, and nested structure.
You'll notice there is some flexibility in the format to accommodate this kind of variation.
If the resume has a dedicated section for skills, use that section's content for the skills array (and don't include the section in the \"Sections\" array).
If the resume DOES NOT have a dedicated section for skills, infer the skills from the content of the resume."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": resume_text},
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_model=ResumeData,
        extra_body=EXTRA_BODY_PARAMS,
    )

    return response

async def call_llm_for_job_ranking(job_description: str, applicant_profile: str) -> JobRanking:
    """Call LLM for job ranking."""

    system_prompt = """You are a job ranking assistant. Your task is to analyze the provided job description and applicant profile to determine the relevance of the applicant's profile to the job.
    
    You will output a job ranking score between 0.0 and 10.0, where 0.0 means no match at all and 10.0 means perfect match.
    You will also provide a brief explanation of your reasoning.
    """
    
    user_prompt = f"""Please analyze this job description and applicant profile and provide a match score and explanation:
    
    # Job Description
    {job_description}
    
    # Applicant Profile
    {applicant_profile}
    
    Format your response as a JSON object with 'score' (a float between 0.0 and 10.0) and 'explanation' (a string).
    """
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # First try with the instructor method
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            response_model=JobRanking,
            extra_body=EXTRA_BODY_PARAMS,
        )
        return response
    except Exception as e:
        logger.warning(f"Error using instructor for job ranking: {e}")
        
        # Fallback to a regular request and parse the response manually
        try:
            # Create OpenAI client without instructor wrapper
            standard_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=OPENROUTER_API_KEY,
                default_headers={
                    "HTTP-Referer": APP_URL,
                    "X-Title": APP_NAME,
                }
            )
            
            response = standard_client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                extra_body=EXTRA_BODY_PARAMS,
            )
            
            # Extract and parse the response content
            import json
            import re
            
            content = response.choices[0].message.content
            # Try to extract JSON if it's wrapped in ```json ... ``` or similar
            json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find a JSON object directly
                json_match = re.search(r'{\s*"score"\s*:.*?"explanation"\s*:.*?}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    # Just use the raw content and hope it's parseable
                    json_str = content
            data = json.loads(json_str)
            return JobRanking(score=float(data.get("score", 0.5)), explanation=data.get("explanation", "No explanation provided"))
        except Exception as fallback_error:
            logger.error(f"Fallback method also failed: {fallback_error}")
            return JobRanking(score=0.0, explanation=f"Error processing request: {str(e)}")

async def call_llm_for_resume_tailoring(job_description: str, applicant_profile: str) -> TailoringSuggestions:
    """Call LLM for resume tailoring."""

    system_prompt = """You are a resume tailoring assistant. Your task is to generate tailored content for a job application based on the provided job description and applicant profile.
Consider the applicant's qualifications and experiences in relation to the job description/requirements.
Provide a list of 3-5 specific, actionable suggestions on how to tailor the profile snippet to better match the job description.
Focus on incorporating keywords, highlighting relevant skills/experience, and using quantifiable achievements where possible.
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Job Description: {job_description}\nApplicant Profile: {applicant_profile}"},
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_model=TailoringSuggestions,
        extra_body=EXTRA_BODY_PARAMS,
    )
    return response
