-- Additive migration if you already ran schema.sql before fleet/QR existed.
-- New installs: skip this, just run schema.sql (it includes the same block).
-- Paste into Supabase SQL editor.

alter table lost_items drop constraint if exists lost_items_status_check;
alter table lost_items add constraint lost_items_status_check
  check (status in ('open','assigned','hunting','matched','resolved'));

alter table lost_items add column if not exists assigned_rover_id text;
alter table lost_items add column if not exists assigned_at timestamptz;
alter table lost_items add column if not exists dispatch_reason text;
alter table lost_items add column if not exists station_id text;
alter table lost_items add column if not exists station_name text;
alter table lost_items add column if not exists station_lat double precision;
alter table lost_items add column if not exists station_lon double precision;

create index if not exists idx_lost_items_rover on lost_items (assigned_rover_id, status);

create table if not exists rovers (
  id            text primary key,
  display_name  text,
  lat           double precision,
  lon           double precision,
  x             double precision,
  y             double precision,
  heading_rad   double precision,
  status        text not null default 'patrol',
  sim_time_s    real,
  last_seen_at  timestamptz not null default now(),
  meta          jsonb
);

create index if not exists idx_rovers_seen on rovers (last_seen_at desc);
alter table rovers enable row level security;
drop policy if exists "public read rovers" on rovers;
create policy "public read rovers" on rovers for select using (true);

create table if not exists kiosk_stations (
  id    text primary key,
  name  text not null,
  lat   double precision not null,
  lon   double precision not null,
  hint  text
);
alter table kiosk_stations enable row level security;
drop policy if exists "public read kiosk_stations" on kiosk_stations;
create policy "public read kiosk_stations" on kiosk_stations for select using (true);

insert into kiosk_stations (id, name, lat, lon, hint) values
  ('suzzallo-circulation', 'Suzzallo Library — Circulation Desk', 47.65585, -122.30895, 'Tape this on the circulation desk.'),
  ('odegaard-helpdesk', 'Odegaard Library — Help Desk', 47.65662, -122.31025, 'Help desk, ground floor.'),
  ('hub-info', 'Husky Union Building — Info Desk', 47.65535, -122.30495, 'Main information desk.'),
  ('gates-atrium', 'Gates Center — Atrium', 47.65328, -122.30505, 'Atrium tables / lost-and-found corner.'),
  ('uwpd-front', 'UWPD / Campus Security — Front Desk', 47.65445, -122.30255, 'Campus security intake.'),
  ('allen-lobby', 'Paul G. Allen Center — Lobby', 47.65340, -122.30580, 'CSE lobby lost-and-found.')
on conflict (id) do update set
  name = excluded.name, lat = excluded.lat, lon = excluded.lon, hint = excluded.hint;

insert into storage.buckets (id, name, public)
values ('lost-item-queries', 'lost-item-queries', true)
on conflict (id) do nothing;

drop policy if exists "public read lost-item-queries" on storage.objects;
create policy "public read lost-item-queries"
  on storage.objects for select
  using (bucket_id = 'lost-item-queries');
