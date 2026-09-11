-- Karna OS v0.3 forward-looking Supabase migration. Run after 001.
alter table public.profiles add column if not exists country text not null default 'India';
alter table public.profiles add column if not exists remote_countries jsonb not null default '["India"]';
alter table public.profiles add column if not exists years_experience numeric not null default 0;
alter table public.profiles add column if not exists minimum_match_score numeric not null default 55 check (minimum_match_score between 0 and 100);
alter table public.profiles add column if not exists last_active_at timestamptz not null default now();
alter table public.profiles add column if not exists deletion_warning_at timestamptz;
alter table public.profiles add column if not exists deletion_scheduled_at timestamptz;

-- Lifecycle policy for the future hosted edition:
-- day 90 inactive: first warning; day 113: final warning; day 120: deletion.
-- A trusted scheduled backend must send notices and perform deletion. Never expose
-- the service-role/secret key to the browser. Local v0.3 never auto-deletes data.
