from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voracity2.models.database import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_name: Mapped[str] = mapped_column(String(31), nullable=False, unique=True)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    process_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    items = relationship("Item", back_populates="sites")
    pages = relationship("Page_", back_populates="sites")
    categories = relationship("Category", back_populates="sites")
