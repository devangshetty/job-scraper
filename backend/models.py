from sqlalchemy import Column, Integer, Text, Float, Boolean, DateTime
from sqlalchemy.sql import func
from database import Base
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class Job(Base):
    __tablename__ = "jobs"

    id              = Column(Integer, primary_key=True, index=True)
    job_title       = Column(Text, nullable=False)
    company         = Column(Text, nullable=False)
    location        = Column(Text)
    salary          = Column(Text)
    description     = Column(Text, nullable=False)
    posted_date     = Column(Text)
    application_url = Column(Text, unique=True, index=True)
    scraped_at      = Column(DateTime, server_default=func.now())
    match_score     = Column(Float)
    matched_skills  = Column(Text)
    missing_skills  = Column(Text)
    is_applied      = Column(Boolean, default=False)
    applied_date    = Column(DateTime)
    notes           = Column(Text)


class Setting(Base):
    __tablename__ = "settings"

    id    = Column(Integer, primary_key=True)
    key   = Column(Text, unique=True, nullable=False)
    value = Column(Text)


class JobBase(BaseModel):
    job_title:       str
    company:         str
    location:        Optional[str] = None
    salary:          Optional[str] = None
    description:     str
    posted_date:     Optional[str] = None
    application_url: str


class JobOut(JobBase):
    id:             int
    scraped_at:     Optional[datetime]
    match_score:    Optional[float]
    matched_skills: Optional[List[str]]
    missing_skills: Optional[List[str]]
    is_applied:     bool
    applied_date:   Optional[datetime]
    notes:          Optional[str]

    class Config:
        from_attributes = True


class JobUpdate(BaseModel):
    is_applied: Optional[bool] = None
    notes:      Optional[str]  = None


class ScrapeRequest(BaseModel):
    keywords:  List[str] = ["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"]
    location:  str       = "Adelaide"
    max_pages: int       = 3


class ScrapeResponse(BaseModel):
    scraped: int
    scored:  int
    message: str


class StatsOut(BaseModel):
    total_jobs:    int
    avg_score:     float
    applied_count: int
    high_match:    int
