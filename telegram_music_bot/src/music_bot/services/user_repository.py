from __future__ import annotations

from pathlib import Path

import aiosqlite


class UserRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS verified_users (
                    user_id INTEGER PRIMARY KEY,
                    verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'en'
                )
                """
            )
            await connection.commit()

    async def is_verified(self, user_id: int) -> bool:
        async with aiosqlite.connect(self._database_path) as connection:
            async with connection.execute(
                "SELECT 1 FROM verified_users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                return await cursor.fetchone() is not None

    async def mark_verified(self, user_id: int) -> None:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute(
                """
                INSERT INTO verified_users (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id,),
            )
            await connection.commit()

    async def get_language(self, user_id: int) -> str | None:
        async with aiosqlite.connect(self._database_path) as connection:
            async with connection.execute(
                "SELECT language FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return str(row[0]) if row else None

    async def set_language(self, user_id: int, language: str) -> None:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute(
                """
                INSERT INTO user_preferences (user_id, language)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
                """,
                (user_id, language),
            )
            await connection.commit()
