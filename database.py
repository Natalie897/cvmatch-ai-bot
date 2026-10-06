import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor

from dotenv import load_dotenv


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
FREE_ANALYSES_LIMIT = 3


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id BIGINT PRIMARY KEY,
                    resume TEXT,
                    analyses_used INTEGER DEFAULT 0
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT,
                    vacancy TEXT,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()


def save_resume(telegram_id: int, resume: str):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO users (
                    telegram_id,
                    resume
                )
                VALUES (%s, %s)

                ON CONFLICT (telegram_id)
                DO UPDATE SET resume = EXCLUDED.resume
            """, (
                telegram_id,
                resume
            ))

        conn.commit()


def get_resume(telegram_id: int):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT resume
                FROM users
                WHERE telegram_id = %s
            """, (
                telegram_id,
            ))

            row = cursor.fetchone()

            if row:
                return row[0]

            return None


def save_analysis(
    telegram_id: int,
    vacancy: str,
    result: dict
):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO analyses (
                    telegram_id,
                    vacancy,
                    result
                )
                VALUES (%s, %s, %s)
            """, (
                telegram_id,
                vacancy,
                json.dumps(
                    result,
                    ensure_ascii=False
                )
            ))

        conn.commit()


def get_last_analyses(
    telegram_id: int,
    limit: int = 5
):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    vacancy,
                    result,
                    created_at
                FROM analyses
                WHERE telegram_id = %s
                ORDER BY id DESC
                LIMIT %s
            """, (
                telegram_id,
                limit
            ))

            return cursor.fetchall()


def get_analysis_by_id(
    analysis_id: int,
    telegram_id: int
):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT result
                FROM analyses
                WHERE id = %s
                AND telegram_id = %s
            """, (
                analysis_id,
                telegram_id
            ))

            row = cursor.fetchone()

            if not row:
                return None

            return json.loads(row[0])


def get_analyses_used(
    telegram_id: int
) -> int:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT analyses_used
                FROM users
                WHERE telegram_id = %s
            """, (
                telegram_id,
            ))

            row = cursor.fetchone()

            if row:
                return row[0]

            return 0


def increment_analyses_used(
    telegram_id: int
):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE users
                SET analyses_used = analyses_used + 1
                WHERE telegram_id = %s
            """, (
                telegram_id,
            ))

        conn.commit()