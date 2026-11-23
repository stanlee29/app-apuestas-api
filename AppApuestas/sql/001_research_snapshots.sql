-- AppApuestas historical snapshots for Supabase Postgres.
-- Apply this migration only to the Supabase project intentionally assigned to AppApuestas.
-- The backend service-role key remains private in Render; never put it in the browser.

create table if not exists public.research_snapshots (
    provider text not null,
    match_id text not null,
    snapshot_type text not null,
    snapshot_date date not null,
    source_timestamp timestamptz null,
    model_version text not null default 'research-1',
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint research_snapshots_pk
        primary key (provider, match_id, snapshot_type, snapshot_date)
);

create index if not exists research_snapshots_match_date_idx
    on public.research_snapshots (match_id, snapshot_date desc);

alter table public.research_snapshots enable row level security;

-- Intentionally no anon/authenticated policies. The backend-only service role
-- bypasses RLS and is never exposed to the browser or mobile client.
revoke all on table public.research_snapshots from anon, authenticated;
grant select, insert, update on table public.research_snapshots to service_role;

create or replace function public.set_research_snapshots_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists research_snapshots_updated_at on public.research_snapshots;
create trigger research_snapshots_updated_at
before update on public.research_snapshots
for each row execute function public.set_research_snapshots_updated_at();
