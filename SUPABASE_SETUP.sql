create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text unique,
  display_name text,
  avatar_url text,
  created_at timestamptz not null default now()
);

create table if not exists public.songs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  prompt text,
  lyrics text,
  audio_url text,
  vocals_url text,
  instrumental_url text,
  status text not null default 'draft',
  visibility text not null default 'private' check (visibility in ('private', 'public')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, display_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.songs enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
on public.profiles
for select
to authenticated
using (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
on public.profiles
for update
to authenticated
using (auth.uid() = id);

drop policy if exists "songs_select_own_or_public" on public.songs;
create policy "songs_select_own_or_public"
on public.songs
for select
to authenticated
using (auth.uid() = user_id or visibility = 'public');

drop policy if exists "songs_insert_own" on public.songs;
create policy "songs_insert_own"
on public.songs
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "songs_update_own" on public.songs;
create policy "songs_update_own"
on public.songs
for update
to authenticated
using (auth.uid() = user_id);

drop policy if exists "songs_delete_own" on public.songs;
create policy "songs_delete_own"
on public.songs
for delete
to authenticated
using (auth.uid() = user_id);
