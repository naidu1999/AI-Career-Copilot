-- Karna OS v1 hosted data contract. Run after 001 and 002 in Supabase SQL Editor.
-- This migration creates per-user records and RLS. The local SQLite application does
-- not automatically switch to this schema; the hosted API adapter must be enabled only
-- after authentication integration tests pass.

alter table public.profiles add column if not exists email text not null default '';
alter table public.profiles add column if not exists current_employer text not null default '';
alter table public.profiles add column if not exists current_role text not null default '';
alter table public.profiles add column if not exists relevant_experience numeric not null default 0;
alter table public.profiles add column if not exists work_authorization text not null default '';
alter table public.profiles add column if not exists needs_sponsorship boolean not null default false;
alter table public.profiles add column if not exists notice_period_days integer not null default 45;
alter table public.profiles add column if not exists expected_compensation text not null default '';

create table if not exists public.user_job_sources (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  name text not null, provider text not null, board_key text not null, enabled boolean not null default true,
  last_scan_at timestamptz, last_success_at timestamptz, last_error text not null default '',
  created_at timestamptz not null default now(), unique(user_id,provider,board_key)
);
create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(), source_key text not null unique, provider text not null,
  title text not null, company text not null, location text not null default '', description text not null default '',
  url text not null, posted_at timestamptz, first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(), employment_type text not null default '',
  fingerprint text not null default '', is_active boolean not null default true,
  liveness_status text not null default 'unknown', raw_json jsonb not null default '{}'
);
create table if not exists public.job_matches (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade, score numeric not null,
  classification text not null, components jsonb not null default '{}', blockers jsonb not null default '[]',
  matched_skills jsonb not null default '[]', missing_skills jsonb not null default '[]',
  reasons jsonb not null default '[]', matcher_version text not null, created_at timestamptz not null default now(),
  unique(user_id,job_id)
);
create table if not exists public.applications (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade, status text not null default 'saved',
  notes text not null default '', recruiter_name text not null default '', recruiter_contact text not null default '',
  follow_up_at timestamptz, interview_at timestamptz, archived boolean not null default false,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,job_id)
);
create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null, title text not null, message text not null, related_id uuid,
  is_read boolean not null default false, created_at timestamptz not null default now()
);
create table if not exists public.account_lifecycle_events (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_type text not null, created_at timestamptz not null default now(), metadata jsonb not null default '{}'
);

create index if not exists evidence_user_status_idx on public.career_evidence(user_id,verification_status);
create index if not exists jobs_active_posted_idx on public.jobs(is_active,posted_at desc);
create index if not exists matches_user_class_score_idx on public.job_matches(user_id,classification,score desc);
create index if not exists applications_user_status_idx on public.applications(user_id,archived,status,updated_at desc);
create index if not exists notifications_user_unread_idx on public.notifications(user_id,is_read,created_at desc);
create index if not exists profiles_last_active_idx on public.profiles(last_active_at);

alter table public.user_job_sources enable row level security;
alter table public.jobs enable row level security;
alter table public.job_matches enable row level security;
alter table public.applications enable row level security;
alter table public.notifications enable row level security;
alter table public.account_lifecycle_events enable row level security;

drop policy if exists "source owner" on public.user_job_sources;
create policy "source owner" on public.user_job_sources for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "authenticated jobs read" on public.jobs;
create policy "authenticated jobs read" on public.jobs for select to authenticated using(true);
drop policy if exists "match owner" on public.job_matches;
create policy "match owner" on public.job_matches for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "application owner" on public.applications;
create policy "application owner" on public.applications for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "notification owner" on public.notifications;
create policy "notification owner" on public.notifications for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "lifecycle owner read" on public.account_lifecycle_events;
create policy "lifecycle owner read" on public.account_lifecycle_events for select using(auth.uid()=user_id);

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('resumes','resumes',false,10485760,array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
drop policy if exists "resume objects owner" on storage.objects;
create policy "resume objects owner" on storage.objects for all to authenticated
using(bucket_id='resumes' and (storage.foldername(name))[1]=auth.uid()::text)
with check(bucket_id='resumes' and (storage.foldername(name))[1]=auth.uid()::text);

create or replace function public.touch_my_activity() returns void language sql security invoker
set search_path=public as $$ update public.profiles set last_active_at=now(),deletion_warning_at=null,
deletion_scheduled_at=null where id=auth.uid(); $$;

create or replace function public.request_my_account_deletion() returns void language plpgsql security invoker
set search_path=public as $$ begin
 update public.profiles set deletion_scheduled_at=now()+interval '7 days' where id=auth.uid();
 insert into public.account_lifecycle_events(user_id,event_type) values(auth.uid(),'deletion_requested');
end $$;

-- A trusted server-side scheduled job must:
-- 1) create first-warning events at 90 inactive days;
-- 2) create final-warning events at 113 inactive days;
-- 3) delete auth.users at 120 inactive days only when warnings are recorded.
-- Never place the service-role key in browser code. Test this workflow in staging first.
