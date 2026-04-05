from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from app.models.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False)
    source_id = Column(String(100), unique=True, nullable=False)
    title = Column(Text, nullable=False)
    authors = Column(Text, default="")
    journal = Column(String(255), default="")
    doi = Column(String(255), default="")
    url = Column(Text, default="")

    # TIMESTAMP WITH TIME ZONE — stores timezone-aware datetimes correctly
    published_at = Column(TIMESTAMP(timezone=True), nullable=True)
    publication_type = Column(String(100), default="unknown")
    trust_score = Column(Float, default=0.5)
    ingested_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
