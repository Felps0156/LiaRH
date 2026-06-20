from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LeadSummary(Base):
    __tablename__ = "lead_summaries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    phone_number: Mapped[str] = mapped_column(String(64), index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)
    final_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="whatsapp")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
