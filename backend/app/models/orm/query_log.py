from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, Boolean
from sqlalchemy.dialects.postgresql import TIMESTAMP
from app.models.database import Base


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, index=True)
    query_text = Column(Text, nullable=False)
    response_text = Column(Text, default="")
    retrieval_latency = Column(Float, default=0.0)
    generation_latency = Column(Float, default=0.0)
    total_latency = Column(Float, default=0.0)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    topic = Column(String(100), default="unknown")
    judge_flagged = Column(Boolean, default=False)
    blocked = Column(Boolean, default=False)
    block_reason = Column(String(255), default="")
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
