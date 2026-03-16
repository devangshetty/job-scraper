from sqlalchemy import Column, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class Job(Base):
    __tablename__ = "jobs"

    id              = Column(Integer, primary_key=True, index=True)
    job_title       = Column(Text, nullable=False)
    company         = Column(Text, nullable=False)
    location        = Column(Text)
    salary          = Column(Text)
    description     = Column(Text)
    posted_date     = Column(Text)
    application_url = Column(Text, unique=True)
    scraped_at      = Column(DateTime, server_default=func.now())
    match_score     = Column(Float, nullable=True)
    matched_skills  = Column(Text)   # JSON array string
    missing_skills  = Column(Text)   # JSON array string
    is_applied      = Column(Boolean, default=False)
    notes           = Column(Text)
    source          = Column(Text)   # 'seek' | 'iworkforsa' | 'indeed'


class Setting(Base):
    __tablename__ = "settings"

    id    = Column(Integer, primary_key=True, index=True)
    key   = Column(Text, unique=True, nullable=False)
    value = Column(Text)
