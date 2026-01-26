from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Date, func, String, Integer

from config import DB_URL, DEBUG

engine = create_async_engine(DB_URL, echo=DEBUG)

session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def create_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class Base(DeclarativeBase):
    created: Mapped[date] = mapped_column(Date, default=func.current_date())
    updated: Mapped[date] = mapped_column(Date, default=func.current_date(), onupdate=func.current_date())


class Threads(Base):
    __tablename__ = 'threads'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, nullable=False)
    assistant_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)


class UsageLog(Base):
    """Логи использования API для rate limiting"""
    __tablename__ = 'usage_log'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)


class UserState(Base):
    """Состояние пользователя (выбранный ассистент)"""
    __tablename__ = 'user_state'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    assistant_id: Mapped[str] = mapped_column(String, nullable=True)


class Conversations(Base):
    """Хранение состояния диалога для Responses API (замена Threads)"""
    __tablename__ = 'conversations'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    assistant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    last_response_id: Mapped[str] = mapped_column(String, nullable=True)
