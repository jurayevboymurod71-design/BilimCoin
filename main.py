"""BilimCoin backend: FastAPI (API) + Aiogram (bot, admin xabarlari, getChatMember)."""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import parse_qsl

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           Message, Update, WebAppInfo)
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from admin import ADMIN_IDS, router as admin_router
from database import (REFERRAL_GEMS, Ad, AdView, Channel, ChannelReward, QSession, SessionLocal, User,
                      Withdrawal, get_or_create_user, get_setting, init_db, seed_defaults, spend_gems)
from questions import BANK

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bilimcoin")

# ---------------- Sozlamalar (environment variables) ----------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.getenv("BOT_USERNAME", "Bilim_Coin_bot")        # @ belgisiz
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")            # https://sizning-app.onrender.com
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:32]
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

MIN_WITHDRAW = 30_000
MIN_FRIENDS = 5
CHANNEL_GEMS = 2
QUESTION_TIME = 15          # soniya
GRACE = 3                   # tarmoq kechikishi uchun qo'shimcha soniya
AD_SECONDS = 15
REWARD_AD_GEMS = 2
MAX_REWARD_ADS_PER_DAY = 30
MAX_BOOST_COST = 1_000_000
# Pul chiqarish so'rovlari shu chatga boradi (shaxsiy ID yoki guruh ID, masalan -1001234567890).
# Berilmasa, hamma ADMIN_IDS ga yuboriladi.
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or 0) or None
NOTIFY_CHATS = [ADMIN_CHAT_ID] if ADMIN_CHAT_ID else sorted(ADMIN_IDS)
DEMO_MODE = os.getenv("DEMO_MODE") == "1"   # 1 bo'lsa, hamma uchun demo-do'st tugmasi ishlaydi (faqat sinov!)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(admin_router)


def reward_for(n: int) -> int:
    """n - savol tartib raqami (1 dan): 1-20 -> 10, 21-100 -> 20, 100 dan keyin -> 30 (oshmaydi)."""
    return 10 if n <= 20 else 20 if n <= 100 else 30


def level_for(n: int) -> str:
    return "Oson" if n <= 20 else "O'rta" if n <= 100 else "Qiyin"


# ---------------- Telegram initData tekshiruvi ----------------
def validate_init_data(init_data: str, max_age: int = 86400) -> dict:
    """https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app"""
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        received = data.pop("hash", None)
        if not received:
            raise ValueError
        check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            raise ValueError
        if time.time() - int(data["auth_date"]) > max_age:
            raise HTTPException(401, "init_data_expired")
        user = json.loads(data["user"])
        return {"user": user, "start_param": data.get("start_param")}
    except HTTPException:
        raise
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, "invalid_init_data")


async def auth_dep(authorization: str = Header(default="")) -> dict:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "tma" or not token:
        raise HTTPException(401, "missing_auth")
    return validate_init_data(token)


async def db():
    async with SessionLocal() as s:
        yield s


def parse_ref(sp: str | None) -> int | None:
    return int(sp[4:]) if sp and sp.startswith("ref_") and sp[4:].isdigit() else None


async def ensure_user(s, auth: dict) -> User:
    u = auth["user"]
    user, _ = await get_or_create_user(
        s, {"id": u["id"], "username": u.get("username"), "first_name": u.get("first_name", "")},
        parse_ref(auth["start_param"]))
    return user


async def profile(s, user: User) -> dict:
    await s.refresh(user)
    done = (await s.execute(select(func.count()).select_from(ChannelReward)
                            .join(Channel, Channel.key == ChannelReward.channel)
                            .where(ChannelReward.user_id == user.id, Channel.active == True))).scalar_one()  # noqa: E712
    total = (await s.execute(select(func.count()).select_from(Channel)
                             .where(Channel.active == True))).scalar_one()  # noqa: E712
    ad_every = int(await get_setting(s, "ad_every", "10"))
    forced = await get_setting(s, "forced_ads", "1") == "1"
    n = user.answered + 1
    return {
        "id": user.id, "first_name": user.first_name, "som": user.som, "gem": user.gem,
        "answered": user.answered, "next_question_no": n, "next_reward": reward_for(n),
        "referrals": user.referrals_count,
        "costs": {"fifty": user.cost_fifty, "time": user.cost_time, "show": user.cost_show},
        "ad_required": user.ad_required,
        "channels_done": done, "channels_total": total, "ad_every": ad_every, "forced_ads": forced,
        "is_admin": user.id in ADMIN_IDS, "demo": DEMO_MODE or user.id in ADMIN_IDS,
        "ref_link": f"https://t.me/{BOT_USERNAME}?startapp=ref_{user.id}",
        "min_withdraw": MIN_WITHDRAW, "min_friends": MIN_FRIENDS,
    }


# ---------------- Kanal obunasi (getChatMember) ----------------
async def is_subscribed(channel: str, uid: int) -> bool:
    try:
        m = await bot.get_chat_member(channel, uid)
    except TelegramAPIError as e:
        log.error("getChatMember(%s) xato: %s  (bot kanalda admin bo'lishi shart!)", channel, e)
        raise HTTPException(502, "channel_check_failed")
    return m.status in ("creator", "administrator", "member") or \
        (m.status == "restricted" and getattr(m, "is_member", False))


def channel_url(ch: str) -> str:
    return f"https://t.me/{ch[1:]}" if ch.startswith("@") else ch


async def active_channels(s) -> list[Channel]:
    return list((await s.execute(select(Channel).where(Channel.active == True)  # noqa: E712
                                 .order_by(Channel.id))).scalars())


async def forced_due(s, n: int) -> bool:
    if await get_setting(s, "forced_ads", "1") != "1":
        return False
    every = int(await get_setting(s, "ad_every", "10"))
    return every > 0 and n % every == 0


# ---------------- Aiogram: bot handlerlari ----------------
@dp.message(CommandStart())
async def cmd_start(m: Message, command: CommandObject):
    async with SessionLocal() as s:  # t.me/bot?start=ref_123 havolasi orqali kelganlarni ham qayd etamiz
        await get_or_create_user(
            s, {"id": m.from_user.id, "username": m.from_user.username, "first_name": m.from_user.first_name},
            parse_ref(command.args))
    kb = None
    if BASE_URL:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎮 O'ynash", web_app=WebAppInfo(url=BASE_URL))]])
    await m.answer("BilimCoin: bilimingizni sinang, so'm va olmos ishlang! 💎", reply_markup=kb)


@dp.callback_query(F.data.startswith("wd:"))
async def withdraw_decision(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    _, action, wid = cb.data.split(":")
    new_status = "paid" if action == "paid" else "rejected"
    async with SessionLocal() as s:
        wd = await s.get(Withdrawal, int(wid))
        if not wd:
            await cb.answer("Topilmadi")
            return
        r = await s.execute(update(Withdrawal).where(Withdrawal.id == wd.id, Withdrawal.status == "pending")
                            .values(status=new_status, processed_at=time.time()))
        if r.rowcount != 1:
            await cb.answer("Allaqachon ko'rib chiqilgan")
            return
        if new_status == "rejected":   # pulni qaytaramiz
            await s.execute(update(User).where(User.id == wd.user_id).values(som=User.som + wd.amount))
        await s.commit()
        uid, amount = wd.user_id, wd.amount
    mark = "✅ TASDIQLANDI" if new_status == "paid" else "❌ RAD ETILDI (pul balansga qaytarildi)"
    if isinstance(cb.message, Message):
        await cb.message.edit_text((cb.message.text or "") + f"\n\n{mark}")
    await cb.answer("Bajarildi")
    try:
        txt = f"✅ {amount:,} so'm kartangizga o'tkazildi.".replace(",", " ") if new_status == "paid" \
            else f"❌ {amount:,} so'm so'rovingiz rad etildi, mablag' balansingizga qaytarildi.".replace(",", " ")
        await bot.send_message(uid, txt)
    except TelegramAPIError:
        pass


# ---------------- FastAPI ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as s:
        await seed_defaults(s)           # 5 ta standart homiy kanal (faqat baza bo'sh bo'lsa)
    task = None
    if BASE_URL:   # production: webhook (Render uxlab qolsa ham Telegram so'rovi uni uyg'otadi)
        await bot.set_webhook(f"{BASE_URL}/webhook/{WEBHOOK_SECRET}", drop_pending_updates=True,
                              allowed_updates=dp.resolve_used_update_types())
    else:          # lokal ishlab chiqish: polling
        await bot.delete_webhook(drop_pending_updates=True)
        task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    yield
    if task:
        task.cancel()
    await bot.session.close()


app = FastAPI(title="BilimCoin API", lifespan=lifespan)
if ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if not hmac.compare_digest(secret, WEBHOOK_SECRET):
        raise HTTPException(404)
    update_obj = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update_obj)
    return {"ok": True}


# ----- 1. Foydalanuvchi -----
@app.get("/api/user")
async def api_user(auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    return await profile(s, user)


# ----- 2. Savol berish (to'g'ri javob serverda qoladi) -----
class QuestionIn(BaseModel):
    subject: str


@app.post("/api/question")
async def api_question(body: QuestionIn, auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    if body.subject not in BANK:
        raise HTTPException(400, "unknown_subject")
    if user.ad_required:
        raise HTTPException(409, "ad_required")
    await s.execute(update(QSession).where(QSession.user_id == user.id, QSession.closed == False)  # noqa: E712
                    .values(closed=True))                      # eski ochiq savollarni yopamiz
    text, options, right = random.choice(BANK[body.subject])
    order = list(range(4))
    random.shuffle(order)
    shuffled = [options[i] for i in order]
    qs = QSession(id=uuid.uuid4().hex, user_id=user.id, correct=order.index(right),
                  deadline=time.time() + QUESTION_TIME)
    s.add(qs)
    await s.commit()
    n = user.answered + 1
    return {"question_id": qs.id, "subject": body.subject, "question": text, "options": shuffled,
            "number": n, "level": level_for(n), "reward": reward_for(n), "time_limit": QUESTION_TIME}


# ----- 3. Javob -----
class AnswerIn(BaseModel):
    question_id: str
    choice: int = Field(ge=-1, le=3)   # -1 = vaqt tugadi


@app.post("/api/answer")
async def api_answer(body: AnswerIn, auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    qs = await s.get(QSession, body.question_id)
    if not qs or qs.user_id != user.id:
        raise HTTPException(404, "question_not_found")
    r = await s.execute(update(QSession).where(QSession.id == qs.id, QSession.closed == False)  # noqa: E712
                        .values(closed=True))                  # bir savolga faqat bitta javob
    if r.rowcount != 1:
        raise HTTPException(409, "already_answered")
    correct = time.time() <= qs.deadline + GRACE and body.choice == qs.correct
    n = user.answered + 1
    reward = reward_for(n) if correct else 0
    vals = {"som": User.som + reward, "answered": User.answered + 1}
    if await forced_due(s, n):
        vals["ad_required"] = True                              # har 10 testdan keyin majburiy reklama
    await s.execute(update(User).where(User.id == user.id).values(**vals))
    await s.commit()
    p = await profile(s, user)
    return {"correct": correct, "correct_index": qs.correct, "reward": reward, **p}


# ----- 4. Yordamchilar (boosters) -----
class BoostIn(BaseModel):
    question_id: str
    boost: Literal["fifty", "time", "show"]


@app.post("/api/boost")
async def api_boost(body: BoostIn, auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    qs = await s.get(QSession, body.question_id)
    if not qs or qs.user_id != user.id:
        raise HTTPException(404, "question_not_found")
    if qs.closed or time.time() > qs.deadline + GRACE:
        raise HTTPException(409, "question_closed")
    used = {u for u in qs.used.split(",") if u}
    if body.boost in used:
        raise HTTPException(409, "boost_already_used")
    cost = getattr(user, f"cost_{body.boost}")
    if not await spend_gems(s, user.id, cost):
        raise HTTPException(402, "not_enough_gems")           # frontend: "Reklama ko'rish" ga yo'naltiradi
    extra: dict = {}
    if body.boost == "fifty":
        extra["remove"] = random.sample([i for i in range(4) if i != qs.correct], 2)
    elif body.boost == "show":
        extra["correct_index"] = qs.correct
    else:
        qs.deadline += 5
        extra["extra_seconds"] = 5
    qs.used = ",".join(sorted(used | {body.boost}))
    await s.execute(update(User).where(User.id == user.id)
                    .values(**{f"cost_{body.boost}": min(cost * 2, MAX_BOOST_COST)}))   # narx 2 barobar oshadi
    await s.commit()
    return {"boost": body.boost, "spent": cost, **extra, **(await profile(s, user))}


# ----- 5. Reklama (server vaqtni o'zi hisoblaydi) -----
class AdStartIn(BaseModel):
    kind: Literal["forced", "reward"]


class AdFinishIn(BaseModel):
    ad_id: str


@app.post("/api/ad/start")
async def ad_start(body: AdStartIn, auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    if body.kind == "forced" and not user.ad_required:
        raise HTTPException(400, "ad_not_required")
    if body.kind == "reward":
        today = (await s.execute(select(func.count()).select_from(AdView).where(
            AdView.user_id == user.id, AdView.kind == "reward", AdView.finished == True,  # noqa: E712
            AdView.started_at > time.time() - 86400))).scalar_one()
        if today >= int(await get_setting(s, "reward_ads_daily", str(MAX_REWARD_ADS_PER_DAY))):
            raise HTTPException(429, "daily_ad_limit")
    ad = AdView(id=uuid.uuid4().hex, user_id=user.id, kind=body.kind, started_at=time.time())
    s.add(ad)
    rows = (await s.execute(select(Ad).where(Ad.active == True))).scalars().all()  # noqa: E712
    creative = random.choice(rows) if rows else None
    if creative:
        creative.shows += 1
    await s.commit()
    return {"ad_id": ad.id, "seconds": AD_SECONDS,
            "ad": {"title": creative.title, "text": creative.text, "link": creative.link} if creative else None}


@app.post("/api/ad/finish")
async def ad_finish(body: AdFinishIn, auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    ad = await s.get(AdView, body.ad_id)
    if not ad or ad.user_id != user.id:
        raise HTTPException(404, "ad_not_found")
    if time.time() - ad.started_at < AD_SECONDS - 1:
        raise HTTPException(425, "ad_not_finished")
    r = await s.execute(update(AdView).where(AdView.id == ad.id, AdView.finished == False)  # noqa: E712
                        .values(finished=True))
    if r.rowcount != 1:
        raise HTTPException(409, "ad_already_claimed")
    if ad.kind == "reward":
        await s.execute(update(User).where(User.id == user.id).values(gem=User.gem + REWARD_AD_GEMS))
    else:
        await s.execute(update(User).where(User.id == user.id).values(ad_required=False))
    await s.commit()
    return await profile(s, user)


# ----- 6. Homiy kanallar (bazadan) -----
class ClaimIn(BaseModel):
    channel: str   # kanal kaliti (key)


@app.get("/api/channels")
async def api_channels(auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    claimed = set((await s.execute(select(ChannelReward.channel)
                                   .where(ChannelReward.user_id == user.id))).scalars())
    return [{"key": c.key, "title": c.title, "url": c.url, "claimed": c.key in claimed, "gems": CHANNEL_GEMS}
            for c in await active_channels(s)]


@app.post("/api/channels/claim")
async def api_channel_claim(body: ClaimIn, auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    ch = (await s.execute(select(Channel).where(Channel.key == body.channel,
                                                Channel.active == True))).scalar_one_or_none()  # noqa: E712
    if not ch:
        raise HTTPException(400, "unknown_channel")
    exists = (await s.execute(select(ChannelReward.id).where(
        ChannelReward.user_id == user.id, ChannelReward.channel == ch.key))).first()
    if exists:
        raise HTTPException(409, "already_claimed")
    if not await is_subscribed(ch.chat, user.id):              # real vaqtda tekshiruv
        raise HTTPException(400, "not_subscribed")
    s.add(ChannelReward(user_id=user.id, channel=ch.key))
    try:
        await s.flush()   # UNIQUE(user_id, channel) ikki marta berishdan himoya qiladi
    except Exception:
        await s.rollback()
        raise HTTPException(409, "already_claimed")
    await s.execute(update(User).where(User.id == user.id).values(gem=User.gem + CHANNEL_GEMS))
    await s.commit()
    return await profile(s, user)


# ----- 7. Pul chiqarish -----
def luhn_ok(num: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(num)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


class WithdrawIn(BaseModel):
    card: str = Field(min_length=12, max_length=25)


@app.post("/api/withdraw")
async def api_withdraw(body: WithdrawIn, auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    card = re.sub(r"\D", "", body.card)
    if len(card) != 16 or not luhn_ok(card):
        raise HTTPException(400, "invalid_card")
    amount = user.som                       # BUTUN balans yechiladi (nolga tushadi)
    if amount < MIN_WITHDRAW:
        raise HTTPException(400, detail={"error": "min_amount", "min": MIN_WITHDRAW})
    if amount > user.som:
        raise HTTPException(400, "insufficient_balance")
    if user.referrals_count < MIN_FRIENDS:
        raise HTTPException(403, detail={"error": "need_friends", "have": user.referrals_count, "need": MIN_FRIENDS})
    pending = (await s.execute(select(Withdrawal.id).where(
        Withdrawal.user_id == user.id, Withdrawal.status == "pending"))).first()
    if pending:
        raise HTTPException(409, "pending_withdrawal_exists")
    # Kanallarga obunani HOZIR tekshiramiz (avval obuna bo'lib, keyin chiqib ketganlarni ushlash uchun)
    chans = await active_channels(s)
    results = await asyncio.gather(*(is_subscribed(c.chat, user.id) for c in chans))
    missing = [c.title for c, ok in zip(chans, results) if not ok]
    if missing or not chans:
        raise HTTPException(403, detail={"error": "need_channels", "missing": missing})
    r = await s.execute(update(User).where(User.id == user.id, User.som >= amount)
                        .values(som=User.som - amount))        # atomik ayirish
    if r.rowcount != 1:
        raise HTTPException(409, "insufficient_balance")
    wd = Withdrawal(user_id=user.id, amount=amount, card=card)
    s.add(wd)
    await s.commit()
    uname = f"@{auth['user']['username']}" if auth["user"].get("username") else "yo'q"
    text = (f"💳 Yangi pul chiqarish so'rovi #{wd.id}\n\n"
            f"👤 Foydalanuvchi ID: {user.id}\n"
            f"🔗 Username: {uname}\n"
            f"💰 Summa: {amount:,} so'm\n"
            f"💳 Karta: {card}\n"
            f"👥 Do'stlar: {user.referrals_count} | ✍️ Javoblar: {user.answered}").replace(",", " ")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"wd:paid:{wd.id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"wd:rej:{wd.id}")]])
    sent = 0
    for chat_id in NOTIFY_CHATS:
        try:
            await bot.send_message(chat_id, text, reply_markup=kb)
            sent += 1
        except TelegramAPIError as e:
            log.error("Admin chat %s ga xabar yuborilmadi: %s", chat_id, e)
    if not sent:
        log.error("Withdrawal #%s: adminga xabar yetmadi! So'rov bazada 'pending' holatda turibdi.", wd.id)
    msg = "So'rovingiz qabul qilindi, 24 soat ichida kartangizga o'tkazib beriladi."
    try:
        await bot.send_message(user.id, "✅ " + msg)
    except TelegramAPIError:
        pass
    return {"ok": True, "message": msg, "withdrawal_id": wd.id, **(await profile(s, user))}


# ----- Demo: test uchun do'st qo'shish (+2 olmos). Faqat adminlar yoki DEMO_MODE=1 -----
@app.post("/api/demo/friend")
async def demo_friend(auth=Depends(auth_dep), s=Depends(db)):
    user = await ensure_user(s, auth)
    if not (DEMO_MODE or user.id in ADMIN_IDS):
        raise HTTPException(403, "demo_disabled")
    await s.execute(update(User).where(User.id == user.id)
                    .values(gem=User.gem + REFERRAL_GEMS, referrals_count=User.referrals_count + 1))
    await s.commit()
    return await profile(s, user)


# Frontend (static/index.html) ni shu serverning o'zidan beramiz. ALOHIDA marshrutlardan KEYIN ulanadi.
if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
