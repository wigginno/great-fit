from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, DateTime, func, JSON
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True)
    cognito_sub = Column(String, unique=True, index=True, nullable=False) # Add cognito_sub
    profile_json = Column(String)  # Store profile as JSON string for PoC
    credits = Column(Integer, default=10, nullable=False)

    jobs = relationship("Job", back_populates="owner", foreign_keys="Job.owner_id")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    company = Column(String)
    description = Column(String) # Assuming this holds cleaned_text or original
    ranking_score = Column(Float, nullable=True)
    ranking_explanation = Column(Text, nullable=True)
    tailoring_suggestions = Column(JSON, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id")) # Re-add owner_id Column for relationship
    created_at = Column(DateTime(timezone=True), server_default=func.now()) # Re-add created_at

    owner = relationship("User", back_populates="jobs", foreign_keys=[owner_id]) # Use standard relationship
