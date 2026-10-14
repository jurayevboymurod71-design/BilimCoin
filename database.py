import os
from sqlalchemy import Column, Integer, String, BigInteger, Boolean, Float, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# SQLite ma'lumotlar bazasi fayli
DATABASE_URL = "sqlite:///./bilimcoin.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()

# 1. Foydalanuvchilar jadvali
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True)
    full_name = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    referrer_id = Column(BigInteger, nullable=True)
    is_admin = Column(Boolean, default=False)

# 2. Homiy kanallar jadvali
class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(BigInteger, unique=True)
    title = Column(String)
    link = Column(String)

# 3. Reklama va e'lonlar jadvali
class Ad(Base):
    __tablename__ = "ads"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String, nullable=True)
    reward = Column(Float, default=0.0)
    link = Column(String)

# 4. Yechib olish so'rovlari jadvali
class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger)
    amount = Column(Float)
    status = Column(String, default="pending") # pending, approved, rejected

# 5. Sessiyalar / O'yinlar jadvali
class Sessionlocal(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger)
    score = Column(Integer, default=0)

# Baza jadval strukturasini yaratish
Base.metadata.create_all(bind=engine)

# Yordamchi funksiyalar
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_setting(key: str, default=None):
    return default

def set_setting(key: str, value):
    pass

def chat_from_url(url: str):
    return url
  
