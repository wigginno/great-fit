from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Union


class UserProfileBase(BaseModel):
    profile_data: dict


class UserProfileCreate(UserProfileBase):
    pass


class UserProfile(UserProfileBase):
    id: int
    owner_email: str

    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    email: str
    cognito_sub: str


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: int
    credits: int
    profile: Union[UserProfile, None] = None

    model_config = ConfigDict(from_attributes=True)


class FormFieldInfo(BaseModel):
    field_id: str  # Unique ID generated by the frontend script
    label: Optional[str] = None  # Text from associated <label> tag
    type: Optional[str] = None  # Input type (e.g., 'text', 'email', 'tel')
    name: Optional[str] = None  # Input 'name' attribute
    placeholder: Optional[str] = None  # Input 'placeholder' attribute


class JobDescriptionInput(BaseModel):
    description: str


class ExtractedJobInfo(BaseModel):
    title: str
    company: str


class JobBase(BaseModel):
    title: str
    company: str
    description: str


class JobCreate(JobBase):
    ranking_score: Union[float, None] = None
    ranking_explanation: Union[str, None] = None
    tailoring_suggestions: Union[list[str], None] = None


class Job(JobBase):
    id: int
    owner_id: int
    ranking_score: Union[float, None] = None
    ranking_explanation: Union[str, None] = None
    tailoring_suggestions: Union[str, None] = None

    model_config = ConfigDict(from_attributes=True)


# --- Request model for raw markdown from Chrome extension ---
# class JobMarkdownRequest(BaseModel):
#     markdown_content: str
class JobContentInput(BaseModel): # Renamed from RawJobInput
    content: str


# --- Pydantic Models for Tailoring Suggestions --- #
class TailoringRequest(BaseModel):
    job_description: str = Field(..., description="The job description to be tailored.")


class TailoringResponse(BaseModel):
    suggestions: list[str] = Field(
        ...,
        description="A list of resume tailored suggestions for the job application.",
    )


# --- Pydantic Model for LLM Cleaned Job Data from Extension --- #
class CleanedJobDescription(BaseModel):
    title: str = Field(
        ..., description="The official job title extracted from the text."
    )
    company: str = Field(
        ..., description="The name of the company hiring, extracted from the text."
    )
    location: str = Field(
        ..., description="The primary location(s) for the job, extracted from the text."
    )
    url: Optional[str] = Field(
        None,
        description="The original URL of the job posting, if available in the source text.",
    )
    cleaned_markdown: str = Field(
        ...,
        description="The full job description, cleaned of irrelevant elements and formatted in markdown, preserving all essential details.",
    )

    model_config = ConfigDict(from_attributes=True)


# --- Pydantic Models for Resume Parsing --- #
class Subsection(BaseModel):
    title: Optional[str] = None
    entries: list[str]


class Section(BaseModel):
    title: str
    subsections: list[Subsection]
    entries: list[str]


class ResumeData(BaseModel):
    sections: list[Section]
    skills: list[str]


# --- Pydantic Model for Job Ranking --- #
class JobRanking(BaseModel):
    score: float = Field(
        ..., description="A score between 0.0 and 10.0 indicating job fit."
    )
    explanation: str = Field(
        ..., description="A brief explanation of the ranking score."
    )
