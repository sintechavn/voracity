from datetime import datetime

# from models.item import Item  # noqa: F401
# from models.site import Site  # noqa: F401
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

# from models.category import Category  # noqa: F401
from voracity2.models.database import Base


class Page_(Base):
    __tablename__ = "pages_new"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id"))
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"))
    category_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    sku: Mapped[str] = mapped_column(String(63))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    updated_by: Mapped[str] = mapped_column(String(100))
    result_text: Mapped[str] = mapped_column(String(200))
    sites = relationship("Site", back_populates="pages")
    categories = relationship("Category", back_populates="pages")
    items = relationship("Item", back_populates="pages")
    UniqueConstraint("site_id", "url", name="categories_unique")
