"""Konsoldan yuklash:  DATABASE_URL=... python import_questions.py savollar.csv"""
import asyncio
import sys

from database import SessionLocal, init_db
from qimport import import_rows, parse_rows


async def main(path: str) -> None:
    await init_db()
    with open(path, "rb") as f:
        rows = parse_rows(f.read(), path)
    async with SessionLocal() as s:
        print(await import_rows(s, rows))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
