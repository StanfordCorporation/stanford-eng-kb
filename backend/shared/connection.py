"""Supabase Postgres connection + pgvector adapter registration.

Serverless note: callers MUST use `get_conn()` per request and close the
connection at the end. No module-level long-lived connection — Vercel
serverless functions are short-lived and Supabase's Supavisor pooler closes
idle connections, which would break the next invocation.

For production on Vercel, use the Supavisor pooler endpoint:
  SUPABASE_DB_HOST=aws-0-<region>.pooler.supabase.com
  SUPABASE_DB_PORT=6543
  SUPABASE_DB_USER=postgres.<project-ref>
"""

import os

import psycopg2
from pgvector.psycopg2 import register_vector


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
