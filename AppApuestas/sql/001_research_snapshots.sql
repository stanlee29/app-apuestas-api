-- Backend-only historical snapshots for AppApuestas.
-- The service-role key remains private in Render and is never sent to the browser.

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
revoke all on table public.research_snapshots from anon, authenticated;
grant select, insert, update, delete on table public.research_snapshots to service_role;

create or replace function public.set_app_research_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
    new.updated_at = pg_catalog.now();
    return new;
end;
$$;

revoke execute on function public.set_app_research_updated_at() from public, anon, authenticated;

drop trigger if exists research_snapshots_updated_at on public.research_snapshots;
create trigger research_snapshots_updated_at
before update on public.research_snapshots
for each row execute function public.set_app_research_updated_at();
