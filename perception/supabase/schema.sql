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
                    check (status in ('open','matched','resolved')),
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
