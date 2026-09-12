create table if not exists public.readings (
  glucose integer not null,
  trend_arrow text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.notify_state (
  id text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

alter table public.readings enable row level security;
alter table public.notify_state enable row level security;

create policy "anon can read readings"
  on public.readings
  for select
  to anon
  using (true);

create policy "anon can read notify state"
  on public.notify_state
  for select
  to anon
  using (true);