-- Karna OS v1.1 hosted continuity additions. Apply after 003_v1_hosted.sql.
alter table public.jobs add column if not exists canonical_key text not null default '';
alter table public.jobs add column if not exists duplicate_count integer not null default 0;
alter table public.user_job_sources add column if not exists last_duration_ms numeric not null default 0;
alter table public.user_job_sources add column if not exists last_status text not null default 'never';
alter table public.user_job_sources add column if not exists consecutive_failures integer not null default 0;
alter table public.user_job_sources add column if not exists cooldown_until timestamptz;
alter table public.user_job_sources add column if not exists duplicates_found integer not null default 0;
alter table public.applications add column if not exists deadline_at timestamptz;
alter table public.applications add column if not exists rejection_reason text not null default '';
alter table public.applications add column if not exists salary_details text not null default '';
alter table public.applications add column if not exists offer_details text not null default '';

create table if not exists public.generated_artifacts (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 job_id uuid not null references public.jobs(id) on delete cascade, kind text not null, content text not null,
 model text not null default '', status text not null default 'draft', metadata jsonb not null default '{}',
 approved_at timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.interview_prep (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 job_id uuid not null references public.jobs(id) on delete cascade, question text not null,
 category text not null default 'general', answer_framework text not null default '',
 star_situation text not null default '', star_task text not null default '', star_action text not null default '',
 star_result text not null default '', completed boolean not null default false, confidence integer not null default 0,
 notes text not null default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.sync_outbox (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 entity_type text not null, entity_id text not null, operation text not null, payload jsonb not null,
 version integer not null default 1, status text not null default 'pending', attempts integer not null default 0,
 next_attempt_at timestamptz, last_error text not null default '', created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create unique index if not exists jobs_canonical_live_idx on public.jobs(canonical_key) where is_active;
create index if not exists artifacts_user_created_idx on public.generated_artifacts(user_id,created_at desc);
create index if not exists interview_user_job_idx on public.interview_prep(user_id,job_id,completed);
create index if not exists outbox_user_pending_idx on public.sync_outbox(user_id,status,next_attempt_at);

alter table public.generated_artifacts enable row level security;
alter table public.interview_prep enable row level security;
alter table public.sync_outbox enable row level security;
drop policy if exists "artifact owner" on public.generated_artifacts;
create policy "artifact owner" on public.generated_artifacts for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "interview owner" on public.interview_prep;
create policy "interview owner" on public.interview_prep for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "outbox owner" on public.sync_outbox;
create policy "outbox owner" on public.sync_outbox for all using(auth.uid()=user_id) with check(auth.uid()=user_id);

-- Verification query: every user-owned public table must have RLS enabled.
do $$
declare missing text;
begin
 select string_agg(c.relname,', ') into missing
 from pg_class c join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='public' and c.relname in
 ('profiles','career_evidence','user_job_sources','job_matches','applications','notifications',
  'generated_artifacts','interview_prep','sync_outbox') and not c.relrowsecurity;
 if missing is not null then raise exception 'RLS missing on: %',missing; end if;
end $$;
