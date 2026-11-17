from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from voracity2 import settings

Base = declarative_base()

engine = create_engine(settings.DATABASE_URL, echo=False, pool_recycle=3600, pool_pre_ping=True)

session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
