import os
from sqlalchemy import Column, Integer, String, BigInteger, Boolean, Float, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# Sozlamalar
REFERRAL_GEMS = 100

DATABASE_URL = "sqlite:///./bilimcoin.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True)
    full_name = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    gems = Column(Integer, default=0)
    referrer_id = Column(BigInteger, nullable=True)
    is_admin = Column(Boolean, default=False)

class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(BigInteger, unique=True)
    title = Column(String)
    link = Column(String)

class ChannelReward(Base):
    __tablename__ = "channel_rewards"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger)
    channel_id = Column(BigInteger)

class Ad(Base):
    __tablename__ = "ads"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String, nullable=True)
    reward = Column(Float, default=0.0)
    link = Column(String)

class AdView(Base):
    __tablename__ = "ad_views"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger)
    ad_id = Column(Integer)

class Withdrawal(Base):
    __tablename__ = "withdrawals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger)
    amount = Column(Float)
    status = Column(String, default="pending")

class QSession(Base):
    __tablename__ = "q_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger)
    score = Column(Integer, default=0)

# Helper functions
def init_db():
    Base.metadata.create_all(bind=engine)

def seed_defaults():
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_or_create_user(db, telegram_id: int, full_name: str = None, referrer_id: int = None):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, full_name=full_name, referrer_id=referrer_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def get_setting(key: str, default=None):
    return default

def set_setting(key: str, value):
    pass

def spend_gems(db, user_id: int, amount: int):
    user = db.query(User).filter(User.telegram_id == user_id).first()
    if user and user.gems >= amount:
        user.gems -= amount
        db.commit()
        return True
    return False

# Baza yaratish
init_db()
