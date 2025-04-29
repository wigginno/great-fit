import re
import logging
import structlog
from typing import Optional, Union
from openai import AsyncOpenAI
from pydantic import BaseModel
from settings import get_settings
from schemas import (
    ResumeData,
    JobRanking,
    CleanedJobDescription,
    TailoringResponse,
)


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

# Load settings
settings = get_settings()

# --- Configure OpenRouter API ---
if not settings.openrouter_api_key:
    logger.error("OPENROUTER_API_KEY not found in environment variables or .env file.")
    raise ValueError(
        "OPENROUTER_API_KEY not found. Ensure it's set in your environment or .env file."
    )

# --- Application Info for OpenRouter ---
APP_NAME = "Great Fit"
APP_URL = "https://github.com/wigginno/great-fit"

# --- Initialize OpenAI client to use OpenRouter ---
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.openrouter_api_key,
    default_headers={
        "HTTP-Referer": APP_URL,
        "X-Title": APP_NAME,
    },
)

# --- Model Configuration ---
MODEL_CONFIG = {
    "resume_parse": {
        "model": "openai/gpt-4.1-mini",
        "temperature": 0.0,
        "top_p": 1,
        "max_tokens": 4096,
    },
    "jd_clean": {
        "model": "openai/gpt-4.1-mini",
        "temperature": 0.0,
        "top_p": 1,
        "max_tokens": 8192,
    },
    "job_rank": {"model": "openai/o4-mini-high", "max_tokens": 8192},
    "resume_tailor": {"model": "openai/o4-mini-high", "max_tokens": 8192},
}
COMMON_OPTS = {"seed": 123}

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
PARSED_RESUME_OUTPUT_EXAMPLE = re.sub(
    r"\n +", "", PARSED_RESUME_OUTPUT_EXAMPLE
).replace("\n", "")


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    model_config: dict,
    response_model: Optional[BaseModel] = None,
    max_retries: int = 3,
) -> Union[str, BaseModel]:
    """Call LLM for a specific task."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    response = await client.beta.chat.completions.parse(
        messages=messages,
        response_format=response_model,
        **model_config,
        **COMMON_OPTS,
    )
    parsed = response.choices[0].message.parsed

    return parsed


# --- Specific LLM Interaction Functions --- #


async def call_llm_for_resume_parsing(resume_text: str) -> Optional[ResumeData]:
    """Call LLM for structured resume parsing."""

    system_prompt = f"""You are a resume parser. Your task is to extract structured information from the provided resume text.
Example output: {PARSED_RESUME_OUTPUT_EXAMPLE}
Major sections may vary based on the resume, as will the subsections, bullets, and nested structure.
You'll notice there is some flexibility in the format to accommodate this kind of variation.
If the resume has a dedicated section for skills, use that section's content for the skills array (and don't include the section in the \"Sections\" array).
If the resume DOES NOT have a dedicated section for skills, infer the skills from the content of the resume."""
    user_prompt = f"Please parse this resume:\n\n{resume_text}"

    response = await call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_config=MODEL_CONFIG["resume_parse"],
        response_model=ResumeData,
    )
    parsed_data = response

    logger.info("Successfully parsed resume")
    return parsed_data


async def call_llm_to_clean_job_description(
    raw_markdown: str,
) -> Optional[CleanedJobDescription]:
    """Uses LLM to clean raw markdown from a job posting webpage and extract key details."""

    system_prompt = f"""You are an expert job description cleaner and parser. You will receive raw text/markdown scraped from a job posting webpage. 
Your task is to:
1. Extract the job title, company name, location, and the original URL if present in the text.
2. Clean the main body of the job description, removing any website navigation, ads, footers, headers, or other irrelevant text.
3. Format the cleaned job description text for readability, using markdown for structure (like headers #, ## and bullet points *). Ensure all essential information (responsibilities, qualifications, benefits, etc.) is preserved.
4. Return ONLY a JSON object adhering to the CleanedJobDescription schema. If the URL is not found in the text, return null for the url field.

Schema:
```json
{CleanedJobDescription.model_json_schema()}
```
"""

    user_prompt = f"Here is the raw job posting markdown:\n\n{raw_markdown}"

    response = await call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_config=MODEL_CONFIG["jd_clean"],
        response_model=CleanedJobDescription,
    )
    cleaned_job_data = response

    return cleaned_job_data


async def call_llm_for_job_ranking(
    job_description: str, applicant_profile: str
) -> JobRanking:
    """Call LLM for job ranking."""

    system_prompt = """You are a job suitability scoring assistant that objectively evaluates how well an applicant matches a job description. You must follow specific scoring criteria to ensure consistent and fair evaluations.  

    SCORING FRAMEWORK (0-10 scale):
    You must calculate the final score based on the following criteria, with each section's weight indicated:

    1. SKILLS MATCH (40% of total score):
       IMPORTANT: Skills demonstrated through work experience/projects carry significantly more weight than skills merely listed in a skills section.
       - Score 9-10: Applicant has demonstrated 90%+ of required technical skills through actual experience/projects
       - Score 7-8: Applicant has demonstrated 70-89% of required skills through experience; remaining skills may be listed but not demonstrated
       - Score 5-6: Applicant has demonstrated core required skills but some key skills are only listed without evidence of application
       - Score 3-4: Applicant has demonstrated few required skills; most are only listed or implied
       - Score 0-2: Applicant has minimal demonstrated skills relevant to the position

    2. EXPERIENCE RELEVANCE (30% of total score):
       - Score 9-10: Substantial experience directly applying the required skills in similar roles/industry; achievements clearly demonstrate mastery
       - Score 7-8: Good experience applying most required skills in related contexts; evidence of successful application
       - Score 5-6: Moderate experience with some required skills; demonstrated in different contexts that require adaptation
       - Score 3-4: Limited direct experience but shows application of transferable skills in other contexts
       - Score 0-2: Minimal experience applying required skills in any context

    3. EDUCATION & CERTIFICATIONS (15% of total score):
       - Score 9-10: Exceeds educational requirements with relevant specialization
       - Score 7-8: Meets all educational requirements with relevant background
       - Score 5-6: Meets basic educational requirements
       - Score 3-4: Slightly below requirements but has compensating factors
       - Score 0-2: Does not meet minimum educational requirements

    4. SOFT SKILLS & CULTURE FIT (15% of total score):
       - Score 9-10: Profile shows strong evidence of required soft skills and values
       - Score 7-8: Profile indicates good alignment with most required soft skills
       - Score 5-6: Some indication of relevant soft skills
       - Score 3-4: Limited evidence of relevant soft skills
       - Score 0-2: No evidence of required soft skills or potential culture fit

    CALCULATION INSTRUCTIONS:
    1. Assess each category separately first with specific scores
    2. Multiply each category score by its percentage weight
    3. Sum the weighted scores for the final score
    4. Round to one decimal place (e.g., 7.3)

    IMPORTANT OUTPUT REQUIREMENTS:
    - Your explanation MUST show your scoring for each category with specific evidence
    - You MUST include your mathematical calculation showing how you derived the final score
    - For skills evaluation, explicitly distinguish between:
        * DEMONSTRATED skills (backed by specific work examples, projects, or achievements) - these should carry 3x more weight
        * LISTED skills (merely mentioned in a skills section without evidence of application) - these carry minimal weight
    - For each required skill in the job description, note whether the applicant has demonstrated it or merely listed it
    - Be concise but thorough in explaining why specific skills/experiences affected each category score
    - Highlight key strengths and gaps objectively
    """

    user_prompt = f"""Analyze the following job description and applicant profile to determine the applicant's suitability score. Follow the scoring framework precisely.

    # Job Description
    {job_description}

    # Applicant Profile
    {applicant_profile}

    Structure your response to include:
    1. Separate scores for each of the four categories (Skills, Experience, Education, Soft Skills)
    2. Evidence for each category score with specific examples from the job description and profile
    3. For the Skills category, make a clear distinction between:
       - DEMONSTRATED skills (supported by specific work experiences or projects)
       - LISTED skills (only mentioned in a skills section without evidence of application)
    4. Your mathematical calculation showing weighted scores
    5. Final score rounded to one decimal place
    6. Brief summary of key strengths and improvement areas
    """

    response = await call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_config=MODEL_CONFIG["job_rank"],
        response_model=JobRanking,
    )
    job_ranking = response

    return job_ranking


async def call_llm_for_resume_tailoring(
    job_description: str, applicant_profile: str
) -> TailoringResponse:
    """Call LLM for resume tailoring."""

    system_prompt = """You are a resume tailoring assistant. Your task is to generate tailored content for a job application based on the provided job description and applicant profile.

The applicant profile may include an 'Analysis of Profile Match to Job' section which contains a detailed breakdown of the applicant's match score. This analysis identifies strengths and weaknesses in the application that you should use to inform your suggestions.

When providing suggestions:
1. Focus on addressing the SPECIFIC GAPS identified in the analysis section (if present)
2. Recommend ways to highlight DEMONSTRATED SKILLS that align with job requirements
3. Suggest how to reframe or add context to experiences that directly address job needs
4. Provide concrete, specific examples of how to enhance sections to better match the job
5. Prioritize suggestions that address the lowest-scoring categories in the analysis

Provide a list of 3-5 specific, actionable suggestions on how to tailor the profile to better match the job description.
Focus on incorporating keywords, highlighting relevant skills/experience, and using quantifiable achievements where possible.

Return the output as a JSON object following the TailoringResponse schema, specifically populating the 'suggestions' field with a JSON list of strings.
"""

    user_prompt = (
        f"Job Description: {job_description}\nApplicant Profile: {applicant_profile}"
    )

    response = await call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_config=MODEL_CONFIG["resume_tailor"],
        response_model=TailoringResponse,
    )
    tailoring_suggestions = response

    return tailoring_suggestions
