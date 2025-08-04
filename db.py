import os
import psycopg2

def get_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL non definita nelle variabili di ambiente")
    return psycopg2.connect(url)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id SERIAL PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    image TEXT
                );
                CREATE TABLE IF NOT EXISTS search_history (
                    id SERIAL PRIMARY KEY,
                    query TEXT NOT NULL,
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            conn.commit()
