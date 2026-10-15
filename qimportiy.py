"""Savollarni CSV / JSON fayldan bazaga yuklash.
Ishlatilishi: 1) /admin botiga faylni yuborish (admin.py)  2) konsoldan: python import_questions.py fayl.csv"""
import csv
import hashlib
import io
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Question
from questions import norm_subject

# Ustun nomlari (katta-kichik harf farq qilmaydi)
COLS = {
    "subject": ("subject", "fan"),
    "text": ("question", "savol", "text"),
    "a": ("a", "option_a", "variant_a"),
    "b": ("b", "option_b", "variant_b"),
    "c": ("c", "option_c", "variant_c"),
    "d": ("d", "option_d", "variant_d"),
    "correct": ("correct", "javob", "answer", "togri", "to'g'ri"),
}
LETTERS = {"a": 0, "b": 1, "c": 2, "d": 3}


def _pick(row: dict, names: tuple) -> str:
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _correct(v: str, opts: list[str]) -> int | None:
    """To'g'ri javob: A-D harfi, 1-4 raqami yoki variantning o'zi (matn)."""
    low = v.strip().lower()
    if low in LETTERS:
        return LETTERS[low]
    if low in ("1", "2", "3", "4"):
        return int(low) - 1
    for i, o in enumerate(opts):
        if o.strip().lower() == low and low:
            return i
    return None


def parse_rows(data: bytes, filename: str) -> list[dict]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Fayl UTF-8 kodlashda bo'lishi kerak")
    if filename.lower().endswith(".json"):
        try:
            rows = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON xato: {e}")
        if isinstance(rows, dict):
            rows = rows.get("questions") or rows.get("savollar") or []
        if not isinstance(rows, list):
            raise ValueError("JSON savollar ro'yxati bo'lishi kerak")
        return [{str(k).strip().lower(): v for k, v in r.items()} for r in rows if isinstance(r, dict)]
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [{(k or "").strip().lower(): v for k, v in r.items()} for r in reader]


def _item(row: dict) -> tuple[dict | None, str | None]:
    subject = norm_subject(_pick(row, COLS["subject"]))
    if not subject:
        return None, "noma'lum fan"
    text = _pick(row, COLS["text"])
    opts = row.get("options")
    opts = [str(o).strip() for o in opts] if isinstance(opts, list) and len(opts) == 4 \
        else [_pick(row, COLS[k]) for k in "abcd"]
    if not text or any(not o for o in opts):
        return None, "savol yoki variant bo'sh"
    if len(text) > 500 or any(len(o) > 200 for o in opts):
        return None, "matn juda uzun"
    if len({o.lower() for o in opts}) < 4:
        return None, "variantlar bir xil"
    correct = _correct(_pick(row, COLS["correct"]), opts)
    if correct is None:
        return None, "to'g'ri javob aniqlanmadi"
    return {"subject": subject, "text": text, "opts": opts, "correct": correct}, None


async def import_rows(s: AsyncSession, rows: list[dict]) -> dict:
    """Qatorlarni tekshirib, bazaga yozadi. Takroriy savollar (fan+matn bir xil) o'tkazib yuboriladi."""
    good, errors, seen = [], [], set()
    for i, r in enumerate(rows, start=2):               # 1-qator sarlavha
        item, err = _item(r)
        if err:
            errors.append(f"{i}-qator: {err}")
            continue
        h = hashlib.sha1(f"{item['subject']}|{item['text'].lower()}".encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        item["hash"] = h
        good.append(item)
    existing: set[str] = set()
    hashes = [g["hash"] for g in good]
    for i in range(0, len(hashes), 500):
        existing.update((await s.execute(
            select(Question.hash).where(Question.hash.in_(hashes[i:i + 500])))).scalars())
    new = [g for g in good if g["hash"] not in existing]
    for i in range(0, len(new), 1000):
        s.add_all([Question(subject=g["subject"], text=g["text"], a=g["opts"][0], b=g["opts"][1],
                            c=g["opts"][2], d=g["opts"][3], correct=g["correct"], hash=g["hash"])
                   for g in new[i:i + 1000]])
        await s.commit()
    return {"total": len(rows), "added": len(new), "skipped": len(rows) - len(errors) - len(new),
            "errors": len(errors), "samples": errors[:5]}
