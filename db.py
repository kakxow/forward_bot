import datetime as dt
from collections.abc import Sequence

import aiogram
from sqlalchemy import Column, Date, Integer, Result, String, delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    """users table."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    chat = Column(Integer, primary_key=True)
    first_name = Column(String(64), nullable=False)
    last_name = Column(String(64))
    username = Column(String(64))
    birthday = Column(Date)

    def __repr__(self) -> str:  # noqa: D105
        return f"<User(first_name='{self.first_name}', last_name='{self.last_name}', username='{self.username}')>"


class WelcomePicture(Base):
    """welcome_picture table, supposed to have only 1 value."""

    __tablename__ = "welcome_picture"

    id = Column(String, primary_key=True)


engine = create_async_engine("sqlite+aiosqlite:///forward.sqlite", pool_size=1)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables() -> None:
    """Create all tables without re-creating if any of them exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def update_user(chat_id: int, telegram_user: aiogram.types.User, updates: dict) -> User:
    """Update certain fields for a user, or create a new one with those certain fields set."""
    async with async_session() as session, session.begin():
        user = await session.get(User, (telegram_user.id, chat_id))
        if not user:
            user = User(
                id=telegram_user.id,
                chat=chat_id,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                username=telegram_user.username,
            )
            session.add(user)
        for name, value in updates.items():
            # Not overwriting possible list values, but extending.
            if isinstance(value, list):
                old_value = getattr(user, name)
                if isinstance(old_value, list):
                    setattr(user, name, old_value + value)
            setattr(user, name, value)
        await session.commit()
        return user


async def fetch_users_with_bdays(chat_id: int) -> Sequence[User]:
    """Return a list of users with bdays set from a chat wih given chat id."""
    async with async_session() as session, session.begin():
        stmt = (
            select(User)
            .where(
                User.chat == chat_id,
                User.birthday.is_not(None),
            )
            .order_by(User.birthday)
        )
        result = await session.scalars(stmt)
        return result.fetchall()


async def fetch_birthday_ppl() -> Result[tuple[int, int]]:
    """Fetch users who have a birthday today."""
    # 2000 for leap years
    today = dt.datetime.now().date().replace(year=2000)  # noqa: DTZ005
    async with async_session() as session, session.begin():
        stmt = select(User.chat, User.id).where(User.birthday == today).order_by(User.chat)
        return await session.execute(stmt)


async def save_pic(pic: str) -> None:
    """Truncate the table and save a welcome picture id to db."""
    async with async_session() as session, session.begin():
        await session.execute(delete(WelcomePicture))
        session.add(WelcomePicture(id=pic))
        await session.commit()


async def load_pic() -> str | None:
    """Load a welcome picture id from db."""
    async with async_session() as session, session.begin():
        pic = await session.scalar(select(WelcomePicture.id).limit(1))
        await session.commit()
        return pic
