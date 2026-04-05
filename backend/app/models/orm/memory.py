from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Text, ARRAY
from sqlalchemy.dialects.postgresql import TIMESTAMP
from pgvector.sqlalchemy import Vector
from app.models.database import Base
from app.config import get_settings

settings = get_settings()


class ConversationMemory(Base):
    __tablename__ = "conversation_memory"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Text, default="default", index=True)
    query_text = Column(Text, nullable=False)
    response_text = Column(Text, default="")
    query_embedding = Column(Vector(settings.embedding_dim))
    retrieved_chunk_ids = Column(ARRAY(Integer), default=[])
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
