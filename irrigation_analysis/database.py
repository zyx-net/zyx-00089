# -*- coding: utf-8 -*-
"""
数据库访问层
"""
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from .config import DATABASE_URL
from .models import Base

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={'check_same_thread': False},
    pool_pre_ping=True,
    pool_recycle=3600,
    isolation_level='SERIALIZABLE'
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def init_db() -> None:
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_db_session() -> Session:
    """获取独立的数据库会话（用于Web应用）"""
    return SessionLocal()
