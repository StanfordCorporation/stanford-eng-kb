-- Run this once against your Supabase Postgres database
-- (Supabase dashboard → SQL Editor → paste + run)

create extension if not exists vector;

create table if not exists documents (
    id         bigserial primary key,
    source     text not null,
    chunk_idx  int  not null,
    content    text not null,
    metadata   jsonb not null default '{}'::jsonb,
    embedding  vector(384) not null,   -- all-MiniLM-L6-v2 dim
    created_at timestamptz not null default now(),
    constraint documents_source_chunk_uq unique (source, chunk_idx)
);

-- Approximate nearest neighbour index for cosine distance
create index if not exists documents_embedding_hnsw
    on documents using hnsw (embedding vector_cosine_ops);

-- Full-text search index for the keyword half of hybrid search
create index if not exists documents_content_fts
    on documents using gin (to_tsvector('english', content));

-- ─── Multi-tenant additions ──────────────────────────────────────────────────
--
-- Every chunk in `documents` is stamped with `metadata->>'org_id'` (and usually
-- 'sub_id'). Retrieval filters by org so customers in different orgs never see
-- each other's data. These two indexes make that filter cheap.

create index if not exists documents_org_idx
    on documents ((metadata->>'org_id'));

create index if not exists documents_sub_idx
    on documents ((metadata->>'sub_id'));

-- Original-file audit log. We chunk + embed at upload time, but keep the full
-- extracted text here so we can re-chunk later (e.g., if CHUNK_SIZE changes) or
-- export the customer's content back to them as Markdown. One row per upload.

create table if not exists documents_raw (
    id              bigserial primary key,
    org_id          text not null,
    sub_id          text not null,
    source          text not null,           -- matches documents.source for the chunks derived from this upload
    source_type     text not null,           -- 'upload' for now; reserve for future sources
    original_name   text,                    -- the file name the customer uploaded (null for pasted text)
    content         text not null,           -- full extracted text
    metadata        jsonb not null default '{}'::jsonb,
    uploaded_at     timestamptz not null default now()
);

create index if not exists documents_raw_org_idx
    on documents_raw (org_id, sub_id);

create unique index if not exists documents_raw_source_uq
    on documents_raw (source);
