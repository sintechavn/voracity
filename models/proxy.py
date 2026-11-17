import logging
from datetime import datetime, timedelta
from enum import IntEnum

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from voracity2.models.database import Base, session

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Status(IntEnum):
    AVAILABLE = 0
    BLOCKED = 98
    DEAD = 99
    NOT_USE = 100


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    group_name: Mapped[str] = mapped_column(String(31), default=0, nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    block_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    block_interval: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def block(self, wait_time: int) -> bool:
        # # ローテーションタイプのプロキシならブロックしない
        # if self.style.upper() == "ROTATE":
        #     return True

        # ブロック間隔が0ならブロックしない
        if self.block_interval == 0:
            return False

        try:
            self.block_count += 1
            self.updated_at = datetime.now()

            if self.block_count >= self.block_interval:
                self.available_at = datetime.now() + timedelta(seconds=wait_time)
                self.block_count = 0
                logger.info(f"{self.id}:{self.url}: blocked for {wait_time} seconds")

            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"block failed:{type(e)}:{str(e)}")
            return False

    @property
    def is_blocked(self) -> bool:
        return self.available_at > datetime.now()
