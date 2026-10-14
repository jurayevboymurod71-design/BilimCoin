"""BilimCoin: ma'lumotlar bazasi (SQLAlchemy 2.0 async).
Lokal: SQLite (aiosqlite). Serverda: PostgreSQL (asyncpg) - DATABASE_URL orqali."""
import os
import re
import time
from typing import AsyncIterator

from sqlalchemy import (BigInteger, Boolean, Float, Integer, String, UniqueConstraint,
                        func, select, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ---------------- Sozlamalar ----------------
START_GEMS = 3          # yangi foydalanuvchining boshlang'ich olmosi
REFERRAL_GEMS = 100     # har bir taklif qilingan do'st uchun olmos

DEFAULT_CHANNELS = [    # birinchi ishga tushishda bazaga yoziladi (keyin /admin orqali boshqariladi)
    ("ch1", "Sokin Kadrlar", "https://t.me/sokinkadirlar"),
    ("ch2", "Asosiy Kanal 1", "https://t.me/asosiykanal_1"),
    ("ch3", "Asosiy Kanal 2", "https://t.me/asosiykanal_2"),
    ("ch4", "Asosiy Kanal 3", "https://t.me/asosiykanal_3"),
    ("ch5", "Asosiy Kanal 4", "https://t.me/asosiykanal_4"),
]


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bilimcoin.db")
    # Render/Railway "postgres://" yoki "postgresql://" beradi -> asyncpg drayveriga o'tkazamiz
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


engine = create_async_engine(_db_url(), pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ---------------- Modellar ----------------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # Telegram ID
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128), default="")
    som: Mapped[int] = mapped_column(BigInteger, default=0)
    gem: Mapped[int] = mapped_column(Integer, default=START_GEMS)
    answered: Mapped[int] = mapped_column(Integer, default=0)          # bajarilgan testlar soni
    referrer_id: Mapped[int | None] = mapped_column(BigInteger)
    referrals_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_fifty: Mapped[int] = mapped_column(Integer, default=2)        # yordamchilar narxi (har ishlatilganda 2x)
    cost_time: Mapped[int] = mapped_column(Integer, default=2)
    cost_show: Mapped[int] = mapped_column(Integer, default=5)
    ad_required: Mapped[bool] = mapped_column(Boolean, default=False)  # majburiy reklama kutilmoqda
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Referral(Base):
    __tablename__ = "referrals"
    referred_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # bitta odam bir marta
    referrer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Channel(Base):
    """Homiy kanallar (admin /admin orqali qo'shadi/o'chiradi)."""
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(256))
    chat: Mapped[str] = mapped_column(String(64))      # getChatMember uchun: @username yoki -100... ID
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ChannelReward(Base):
    """Foydalanuvchi qaysi kanal uchun olmos olgani (ikki marta bermaslik uchun UNIQUE)."""
    __tablename__ = "channel_rewards"
    __table_args__ = (UniqueConstraint("user_id", "channel"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel: Mapped[str] = mapped_column(String(64))   # Channel.key
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Ad(Base):
    """Reklama kreativlari (admin boshqaradi)."""
    __tablename__ = "ads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(String(500))
    link: Mapped[str] = mapped_column(String(256), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    shows: Mapped[int] = mapped_column(Integer, default=0)


class AdView(Base):
    """Foydalanuvchi ko'rgan reklama (server vaqtni o'zi hisoblaydi)."""
    __tablename__ = "ad_views"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(10))      # forced | reward
    started_at: Mapped[float] = mapped_column(Float)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    card: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | paid | rejected
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    processed_at: Mapped[float | None] = mapped_column(Float)


class QSession(Base):
    """Berilgan savol. To'g'ri javob faqat shu yerda (serverda) saqlanadi."""
    __tablename__ = "question_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    correct: Mapped[int] = mapped_column(Integer)
    deadline: Mapped[float] = mapped_column(Float)
    used: Mapped[str] = mapped_column(String(32), default="")   # ishlatilgan yordamchilar
    closed: Mapped[bool] = mapped_column(Boolean, default=False)


class Setting(Base):
    """Admin sozlamalari: ad_every, forced_ads, reward_ads_daily ..."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))


# ---------------- Funksiyalar ----------------
async def init_db() -> None:
    """Jadvallarni yaratadi (mavjud bo'lsa tegmaydi)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: s=Depends(get_db)."""
    async with SessionLocal() as session:
        yield session


def chat_from_url(url: str) -> str | None:
    """https://t.me/nom -> @nom. Invite (+...) havolalar uchun None: chat ID qo'lda beriladi."""
    m = re.match(r"^(?:https?://)?t\.me/([A-Za-z][A-Za-z0-9_]{3,})/?$", url.strip())
    return "@" + m.group(1) if m else None


async def seed_defaults(s: AsyncSession) -> None:
    """Birinchi ishga tushishda standart homiy kanallarni yozadi (faqat jadval bo'sh bo'lsa)."""
    count = (await s.execute(select(func.count()).select_from(Channel))).scalar_one()
    if count == 0:
        for key, title, url in DEFAULT_CHANNELS:
            s.add(Channel(key=key, title=title, url=url, chat=chat_from_url(url)))
        await s.commit()


async def get_setting(s: AsyncSession, key: str, default: str) -> str:
    row = await s.get(Setting, key)
    return row.value if row else default


async def set_setting(s: AsyncSession, key: str, value: str) -> None:
    row = await s.get(Setting, key)
    if row:
        row.value = value
    else:
        s.add(Setting(key=key, value=value))
    await s.commit()


async def get_or_create_user(s: AsyncSession, tg: dict, ref_id: int | None = None) -> tuple[User, bool]:
    """Foydalanuvchini topadi yoki yaratadi. Referal faqat YANGI foydalanuvchi uchun hisoblanadi
    (o'zini o'zi taklif qilish va ikki marta hisoblash mumkin emas). Qaytaradi: (user, yangi_mi)."""
    uid = tg["id"]
    user = await s.get(User, uid)
    if user:
        name, uname = tg.get("first_name") or "", tg.get("username")
        if user.first_name != name or user.username != uname:      # ism/username o'zgargan bo'lsa yangilaymiz
            user.first_name, user.username = name, uname
            await s.commit()
        return user, False
    referrer = await s.get(User, ref_id) if ref_id and ref_id != uid else None
    user = User(id=uid, username=tg.get("username"), first_name=tg.get("first_name") or "",
                referrer_id=referrer.id if referrer else None)
    s.add(user)
    try:
        await s.flush()
    except IntegrityError:           # parallel so'rov allaqachon yaratib qo'ygan
        await s.rollback()
        return await s.get(User, uid), False
    if referrer:
        s.add(Referral(referred_id=uid, referrer_id=referrer.id))
        await s.execute(update(User).where(User.id == referrer.id)
                        .values(gem=User.gem + REFERRAL_GEMS, referrals_count=User.referrals_count + 1))
    await s.commit()
    return user, True


async def spend_gems(s: AsyncSession, uid: int, cost: int) -> bool:
    """Atomik ayirish: balans yetmasa 0 qator o'zgaradi (race condition bo'lmaydi).
    Commit chaqiruvchi tomonidan qilinadi."""
    r = await s.execute(update(User).where(User.id == uid, User.gem >= cost).values(gem=User.gem - cost))
    return r.rowcount == 1
    
