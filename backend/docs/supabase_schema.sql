create extension if not exists "pgcrypto";

create table if not exists sessions (
  session_id text primary key,
  created_at timestamptz not null default now()
);

create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  session_id text not null references sessions(session_id) on delete cascade,
  role text not null,
  content text not null,
  created_at timestamptz not null default now()
);


