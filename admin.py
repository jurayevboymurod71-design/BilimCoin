"""Admin panel (/admin). Faqat ADMIN_IDS dagilar uchun; boshqalarga bot umuman javob bermaydi."""
import os
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardButton as B
from aiogram.types import InlineKeyboardMarkup as KB
from aiogram.types import Message
from sqlalchemy import delete, func, select

from database import (Ad, Channel, Question, SessionLocal, User, Withdrawal, chat_from_url, get_setting,
                      set_setting)
from qimport import import_rows, parse_rows
from questions import SUBJECTS

ADMIN_IDS = {int(x) for x in re.split(r"[,\s]+", os.getenv("ADMIN_IDS", "8140503158")) if x.isdigit()}
if os.getenv("ADMIN_CHAT_ID", "").isdigit():      # shaxsiy ADMIN_CHAT_ID ham admin hisoblanadi
    ADMIN_IDS.add(int(os.environ["ADMIN_CHAT_ID"]))

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))          # oddiy foydalanuvchilar uchun handler ishlamaydi
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

HELP = ("🛠 Admin panel\n\n"
        "Buyruqlar:\n"
        "/addch <havola> | <nom> | [chat_id]  — homiy kanal qo'shish\n"
        "  masalan: /addch https://t.me/kanal | Kanal nomi\n"
        "  (maxfiy kanal bo'lsa 3-qismga -100... ID yozing)\n"
        "/addad <sarlavha> | <matn> | [havola]  — reklama qo'shish\n"
        "/setads <son>  — har nechta savoldan keyin majburiy reklama\n"
        "📥 Savollar: CSV yoki JSON faylni shu botga yuboring (hisobot: ❓ Savollar tugmasi)\n\n"
        "O'chirish, yoqish/o'chirish va sozlamalar — pastdagi tugmalarda.\n"
        "Bot homiy kanallarda ADMIN bo'lishi shart.")


def menu_kb() -> KB:
    return KB(inline_keyboard=[
        [B(text="📢 Kanallar", callback_data="adm:channels"), B(text="📺 Reklamalar", callback_data="adm:ads")],
        [B(text="⚙️ Sozlamalar", callback_data="adm:settings"), B(text="📊 Statistika", callback_data="adm:stats")],
        [B(text="❓ Savollar", callback_data="adm:questions")]])


def back_row() -> list:
    return [B(text="⬅️ Menyu", callback_data="adm:menu")]


async def send(ev, text: str, kb: KB | None = None):
    if isinstance(ev, CallbackQuery):
        try:
            await ev.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass
        await ev.answer()
    else:
        await ev.answer(text, reply_markup=kb)


async def view_channels(ev):
    async with SessionLocal() as s:
        rows = (await s.execute(select(Channel).order_by(Channel.id))).scalars().all()
    kb = [[B(text=f"{'✅' if c.active else '⏸'} {c.title}", callback_data=f"adm:togch:{c.id}"),
           B(text="🗑", callback_data=f"adm:delch:{c.id}")] for c in rows]
    text = "📢 Homiy kanallar (nomni bossangiz yoqiladi/o'chadi, 🗑 o'chiradi):\n\n" + \
           ("\n".join(f"{c.id}. {c.title} — {c.url}" for c in rows) or "Hozircha yo'q") + \
           "\n\nQo'shish: /addch <havola> | <nom>"
    await send(ev, text, KB(inline_keyboard=kb + [back_row()]))


async def view_ads(ev):
    async with SessionLocal() as s:
        rows = (await s.execute(select(Ad).order_by(Ad.id))).scalars().all()
    kb = [[B(text=f"{'✅' if a.active else '⏸'} {a.title}", callback_data=f"adm:togad:{a.id}"),
           B(text="🗑", callback_data=f"adm:delad:{a.id}")] for a in rows]
    text = "📺 Reklamalar (faol reklamalar navbat bilan ko'rsatiladi):\n\n" + \
           ("\n".join(f"{a.id}. {a.title} — ko'rsatildi: {a.shows}" for a in rows) or "Hozircha yo'q") + \
           "\n\nQo'shish: /addad <sarlavha> | <matn> | [havola]"
    await send(ev, text, KB(inline_keyboard=kb + [back_row()]))


async def view_settings(ev):
    async with SessionLocal() as s:
        every = await get_setting(s, "ad_every", "10")
        forced = await get_setting(s, "forced_ads", "1") == "1"
        daily = await get_setting(s, "reward_ads_daily", "30")
    text = (f"⚙️ Reklama sozlamalari\n\nMajburiy reklama: {'yoqilgan' if forced else 'o‘chirilgan'}\n"
            f"Har {every} savoldan keyin\nBir kunda mukofotli reklama limiti: {daily} ta")
    kb = KB(inline_keyboard=[
        [B(text="🔁 Majburiy reklamani yoqish/o'chirish", callback_data="adm:forced")],
        [B(text=f"Har {n}", callback_data=f"adm:every:{n}") for n in (5, 10, 15, 20)],
        [B(text=f"Kunlik {n}", callback_data=f"adm:daily:{n}") for n in (10, 30, 50)],
        back_row()])
    await send(ev, text, kb)


async def view_stats(ev):
    async with SessionLocal() as s:
        users = (await s.execute(select(func.count()).select_from(User))).scalar_one()
        som = (await s.execute(select(func.coalesce(func.sum(User.som), 0)))).scalar_one()
        pend = (await s.execute(select(func.count()).select_from(Withdrawal)
                                .where(Withdrawal.status == "pending"))).scalar_one()
    await send(ev, f"📊 Foydalanuvchilar: {users}\nJami balans: {som:,} so'm\nKutilayotgan to'lovlar: {pend}"
               .replace(",", " "), KB(inline_keyboard=[back_row()]))


async def view_questions(ev):
    async with SessionLocal() as s:
        rows = (await s.execute(select(Question.subject, func.count()).where(Question.active == True)  # noqa: E712
                                .group_by(Question.subject))).all()
    cnt = dict(rows)
    lines = "\n".join(f"{name} ({key}): {cnt.get(key, 0)}" for key, name in SUBJECTS.items())
    text = (f"❓ Bazadagi savollar:\n\n{lines}\n\nJami: {sum(cnt.values())}\n\n"
            "Qo'shish: CSV yoki JSON faylni shu botga yuboring.\n"
            "CSV ustunlari: subject,question,a,b,c,d,correct (correct: A-D yoki 1-4).\n"
            "Fan kalitlari: " + ", ".join(SUBJECTS) + "\n"
            "Bazasi bo'sh fanlar uchun kichik standart savollar ishlatiladi.")
    await send(ev, text, KB(inline_keyboard=[back_row()]))


@router.message(F.document)
async def import_file(m: Message):
    doc = m.document
    name = (doc.file_name or "").lower()
    if not name.endswith((".csv", ".json", ".txt")):
        await m.answer("Faqat .csv yoki .json fayl yuboring.")
        return
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await m.answer("Fayl 20 MB dan katta (Telegram cheklovi). Bir nechta faylga bo'lib yuboring.")
        return
    await m.answer("⏳ Yuklanmoqda...")
    try:
        data = (await m.bot.download(doc)).read()
        rows = parse_rows(data, name)
    except ValueError as e:
        await m.answer(f"❌ {e}")
        return
    async with SessionLocal() as s:
        res = await import_rows(s, rows)
    msg = (f"✅ Qo'shildi: {res['added']}\nTakroriy/o'tkazilgan: {res['skipped']}\n"
           f"Xato qatorlar: {res['errors']}\nJami qator: {res['total']}")
    if res["samples"]:
        msg += "\n\nXato namunalari:\n" + "\n".join(res["samples"])
    await m.answer(msg)


@router.message(Command("admin"))
async def cmd_admin(m: Message):
    await m.answer(HELP, reply_markup=menu_kb())


@router.message(Command("addch"))
async def cmd_addch(m: Message, command: CommandObject):
    parts = [p.strip() for p in (command.args or "").split("|")]
    url = parts[0]
    chat = parts[2] if len(parts) > 2 and parts[2] else chat_from_url(url)
    title = parts[1] if len(parts) > 1 and parts[1] else url.rstrip("/").rsplit("/", 1)[-1]
    if not url.startswith("http") or not chat:
        await m.answer("Format: /addch https://t.me/kanal | Nomi\n(maxfiy/invite havola bo'lsa 3-qismga chat ID yozing)")
        return
    key = re.sub(r"\W", "", chat.lstrip("@")).lower()[:60]
    async with SessionLocal() as s:
        if (await s.execute(select(Channel).where(Channel.key == key))).first():
            await m.answer("Bu kanal allaqachon bor.")
            return
        s.add(Channel(key=key, title=title, url=url, chat=chat))
        await s.commit()
    warn = ""
    try:
        me = await m.bot.me()
        st = (await m.bot.get_chat_member(chat, me.id)).status
        if st not in ("administrator", "creator"):
            warn = "\n⚠️ Bot bu kanalda admin emas — obunani tekshira olmaydi!"
    except TelegramAPIError:
        warn = "\n⚠️ Kanalni tekshirib bo'lmadi: botni kanalga admin qiling va havolani tekshiring."
    await m.answer(f"✅ Qo'shildi: {title}{warn}")


@router.message(Command("addad"))
async def cmd_addad(m: Message, command: CommandObject):
    parts = [p.strip() for p in (command.args or "").split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        await m.answer("Format: /addad Sarlavha | Matn | https://havola (havola ixtiyoriy)")
        return
    async with SessionLocal() as s:
        s.add(Ad(title=parts[0][:120], text=parts[1][:480], link=parts[2][:250] if len(parts) > 2 else ""))
        await s.commit()
    await m.answer("✅ Reklama qo'shildi.")


@router.message(Command("setads"))
async def cmd_setads(m: Message, command: CommandObject):
    if not (command.args or "").strip().isdigit() or not 1 <= int(command.args) <= 100:
        await m.answer("Format: /setads 10  (1 dan 100 gacha)")
        return
    async with SessionLocal() as s:
        await set_setting(s, "ad_every", command.args.strip())
    await m.answer(f"✅ Endi har {command.args.strip()} savoldan keyin majburiy reklama chiqadi.")


@router.callback_query(F.data.startswith("adm:"))
async def adm_cb(cb: CallbackQuery):
    _, act, *arg = cb.data.split(":")
    val = arg[0] if arg else None
    if act in ("togch", "delch", "togad", "delad"):
        model = Channel if act.endswith("ch") else Ad
        async with SessionLocal() as s:
            obj = await s.get(model, int(val))
            if obj:
                if act.startswith("del"):
                    await s.execute(delete(model).where(model.id == obj.id))
                else:
                    obj.active = not obj.active
                await s.commit()
        return await (view_channels(cb) if model is Channel else view_ads(cb))
    if act in ("forced", "every", "daily"):
        async with SessionLocal() as s:
            if act == "forced":
                cur = await get_setting(s, "forced_ads", "1")
                await set_setting(s, "forced_ads", "0" if cur == "1" else "1")
            elif act == "every":
                await set_setting(s, "ad_every", val)
            else:
                await set_setting(s, "reward_ads_daily", val)
        return await view_settings(cb)
    views = {"menu": None, "channels": view_channels, "ads": view_ads, "settings": view_settings, "stats": view_stats, "questions": view_questions}
    fn = views.get(act)
    await (fn(cb) if fn else send(cb, HELP, menu_kb()))
