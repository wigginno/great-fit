from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True)
    profile_json = Column(String)  # Store profile as JSON string for PoC

    jobs = relationship("Job", back_populates="owner", foreign_keys="Job.owner_id")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    company = Column(String)
    description = Column(String)
    ranking_score = Column(Float, nullable=True)
    ranking_explanation: Mapped[str | None] = Column(String, nullable=True)
    tailoring_suggestions: Mapped[str | None] = Column(String, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    owner: Mapped["User"] = relationship(
        "User", back_populates="jobs", foreign_keys=[owner_id]
    )
