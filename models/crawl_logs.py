from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from voracity2.models.database import Base, engine


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer)
    site_name: Mapped[str] = mapped_column(String(31))
    page_pending: Mapped[int] = mapped_column(Integer)
    page_running: Mapped[int] = mapped_column(Integer)
    page_end_ok: Mapped[int] = mapped_column(Integer)
    page_end_ng: Mapped[int] = mapped_column(Integer)
    page_total: Mapped[int] = mapped_column(Integer)
    product_total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


if __name__ == "__main__":
    Base.metadata.create_all(engine)
