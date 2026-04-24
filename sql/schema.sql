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
