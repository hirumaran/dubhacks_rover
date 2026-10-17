-- ============================================================
-- Lost-Item Rover: Supabase schema
-- Paste this whole file into Supabase Dashboard -> SQL Editor -> Run.
-- Idempotent: safe to run multiple times.
-- ============================================================

-- ---------- 1. Core tables ----------
create extension if not exists pgcrypto;

create table if not exists sightings (
  id            uuid primary key default gen_random_uuid(),
  object_id     text not null,               -- stable tracker ID, e.g. OBJ-183012-3
  label         text not null,               -- short class name from Isaac
  description   text,                        -- one-sentence VLM description
  color         text,
  confidence    real not null default 0,     -- 0..1
  bbox_norm     jsonb,                       -- [x1,y1,x2,y2] normalized 0..1
  camera_idx    int,                         -- 0..3 (front,left,back,right)
  event         text not null default 'seen' -- new | seen | moved | gone
                check (event in ('new','seen','moved','gone')),
  image_url     text,                        -- storage object path inside the bucket
  geotag        jsonb not null,              -- {x,y,lat,lon,bearing_deg,range_m,scheme}
  rover_pose    jsonb,                       -- {x,y,heading_rad,sim_time_s}
  sim_time_s    real,
  model_backend text,                        -- transformers|sdk|mock (for debugging)
  created_at    timestamptz not null default now()
);

create index if not exists idx_sightings_object on sightings (object_id);
create index if not exists idx_sightings_time   on sightings (created_at desc);
create index if not exists idx_sightings_label  on sightings (label);

create table if not exists lost_items (
  id                uuid primary key default gen_random_uuid(),
  created_by        text,                      -- anon user id from the web branch
  query_text        text,                      -- typed description ("green water bottle")
  query_image_url   text,                      -- storage path of uploaded photo (optional)
  status            text not null default 'open'
                    check (status in ('open','assigned','hunting','matched','resolved')),
  matched_object_id text,
  match_confidence  real,
  match_reason      text,                      -- human-readable why it matched
  created_at        timestamptz not null default now(),
  resolved_at       timestamptz
);

create index if not exists idx_lost_items_status on lost_items (status, created_at desc);

-- ---------- 2. Optional pgvector (skip if unavailable) ----------
-- If the pgvector extension is enabled we add an embedding column for
-- embedding-based matching later. Run just the enabled variant manually if needed:
--   create extension if not exists vector;
--   alter table sightings add column embedding vector(512);
--   create index on sightings using ivfflat (embedding vector_cosine_ops) with (lists = 100);
--   -- queries:
--   -- select id, 1 - (embedding <=> :query_vec) as sim from sightings order by sim desc limit 5;

-- ---------- 3. Row level security ----------
alter table sightings  enable row level security;
alter table lost_items enable row level security;

-- Rover writes with the SERVICE key (bypasses RLS). Students read via anon:
drop policy if exists "public read sightings" on sightings;
create policy "public read sightings"
  on sightings for select using (true);

-- Students can post lost-item reports and read their own status:
drop policy if exists "public insert lost_items" on lost_items;
create policy "public insert lost_items"
  on lost_items for insert with check (true);

drop policy if exists "public read lost_items" on lost_items;
create policy "public read lost_items"
  on lost_items for select using (true);

-- ---------- 4. Storage bucket for image crops ----------
insert into storage.buckets (id, name, public)
values ('sightings-crops', 'sightings-crops', true)
on conflict (id) do nothing;

-- Public read of crops; writes only service role (default).
drop policy if exists "public read crops" on storage.objects;
create policy "public read crops"
  on storage.objects for select
  using (bucket_id = 'sightings-crops');

-- ---------- 5. Convenience view: latest-known location per object ----------
create or replace view recent_sightings as
select distinct on (object_id)
  object_id, label, description, color, confidence, image_url,
  geotag, rover_pose, sim_time_s, event, created_at
from sightings
where event <> 'gone'
order by object_id, created_at desc;

-- ---------- 6. Fleet + kiosk dispatch (QR -> cloud -> closest rover) ----------
-- Safe to re-run. Existing lost_items tables get new columns via IF NOT EXISTS.

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
  id            text primary key,            -- ROVER_ID env, e.g. mk1
  display_name  text,
  lat           double precision,
  lon           double precision,
  x             double precision,            -- Webots ENU meters
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
create policy "public read rovers"
  on rovers for select using (true);

create table if not exists kiosk_stations (
  id    text primary key,
  name  text not null,
  lat   double precision not null,
  lon   double precision not null,
  hint  text
);

alter table kiosk_stations enable row level security;
drop policy if exists "public read kiosk_stations" on kiosk_stations;
create policy "public read kiosk_stations"
  on kiosk_stations for select using (true);

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
