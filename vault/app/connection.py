"""Supabase Postgres connection + pgvector adapter registration."""

import os
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    conn = psycopg2.connect(
        host=os.environ["SUPABASE_DB_HOST"],
        dbname=os.environ.get("SUPABASE_DB_NAME", "postgres"),
        user=os.environ.get("SUPABASE_DB_USER", "postgres"),
        password=os.environ["SUPABASE_DB_PASSWORD"],
        port=int(os.environ.get("SUPABASE_DB_PORT", "5432")),
        sslmode="require",
    )
    register_vector(conn)
    return conn


conn = get_conn()
cur = conn.cursor()
