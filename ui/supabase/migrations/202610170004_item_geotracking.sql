-- Precise item positions are server-only. Public listing coordinates remain rounded.
alter table public.found_items add column if not exists last_seen_at timestamptz;
alter table public.found_items add column if not exists sighting_count bigint not null default 1;
create table public.found_item_geotracks (
 found_item_id uuid primary key references public.found_items on delete cascade,
 tracker_id uuid not null unique,
 tracking_scope text not null check(length(tracking_scope) between 1 and 160),
 latitude double precision not null check(latitude between -90 and 90),
 longitude double precision not null check(longitude between -180 and 180),
 accuracy_m double precision not null check(accuracy_m between 0.1 and 25),
 first_seen_at timestamptz not null,
 last_seen_at timestamptz not null,
 sighting_count bigint not null default 0
);
create index on public.found_item_geotracks(tracking_scope,latitude,longitude);
create table public.found_item_geosightings (
 sighting_id uuid primary key,
 found_item_id uuid not null references public.found_items on delete cascade,
 seen_at timestamptz not null
);
alter table public.found_item_geotracks enable row level security;
alter table public.found_item_geosightings enable row level security;
revoke all on public.found_item_geotracks,public.found_item_geosightings from public,anon,authenticated;
grant all on public.found_item_geotracks,public.found_item_geosightings to service_role;

create function public.nearby_item_geotracks(p_lat double precision,p_lng double precision,p_scope text,p_demo boolean,p_radius double precision default 3)
returns table(id uuid,title text,description text,category text,color text,image_path text,distance_m double precision)
language sql stable security definer set search_path='' as $$
 select f.id,f.title,f.description,f.category,f.color,f.image_path,
 sqrt(power((g.latitude-p_lat)*111320,2)+power((g.longitude-p_lng)*111320*cos(radians(p_lat)),2)) as distance_m
 from public.found_item_geotracks g join public.found_items f on f.id=g.found_item_id
 where g.tracking_scope=p_scope and f.is_demo=p_demo and f.status='available'
 and sqrt(power((g.latitude-p_lat)*111320,2)+power((g.longitude-p_lng)*111320*cos(radians(p_lat)),2)) <= least(10,greatest(1,p_radius)+g.accuracy_m)
 order by distance_m,f.id;
$$;

-- The short SQL transaction serializes final writes, not the slow AI calls.
-- A concurrent, unseen nearby insertion makes the caller repeat the visual comparison.
create function public.commit_item_geosighting(p_sighting uuid,p_tracker uuid,p_row jsonb,p_geo jsonb,p_duplicate uuid default null,p_checked uuid[] default '{}')
returns jsonb language plpgsql security definer set search_path='' as $$
declare
 v_id uuid; v_created boolean:=false; v_seen timestamptz; v_lat double precision; v_lng double precision;
 v_accuracy double precision; v_scope text; v_demo boolean; v_result public.found_items; v_inserted integer;
begin
 perform pg_advisory_xact_lock(hashtext('campus_scout_item_geo_commit'));
 v_seen:=(p_row->>'discovered_at')::timestamptz;
 v_lat:=(p_geo->>'latitude')::double precision; v_lng:=(p_geo->>'longitude')::double precision;
 v_accuracy:=(p_geo->>'accuracy_m')::double precision; v_scope:=p_geo->>'scope'; v_demo:=(p_row->>'is_demo')::boolean;
 if p_sighting is null or p_tracker is null or v_seen is null or v_demo is null or v_scope is null or length(v_scope) not between 1 and 160
 or v_lat is null or not(v_lat between -90 and 90) or v_lng is null or not(v_lng between -180 and 180)
 or v_accuracy is null or not(v_accuracy between 0.1 and 25) then raise exception 'Invalid private geotracking metadata'; end if;
 select found_item_id into v_id from public.found_item_geosightings where sighting_id=p_sighting;
 if v_id is not null then
  if not exists(select 1 from public.found_items where id=v_id and is_demo=v_demo) then raise exception 'Sighting scope mismatch'; end if;
  select * into v_result from public.found_items where id=v_id;
  return jsonb_build_object('action','duplicate','item',to_jsonb(v_result),'idempotent',true);
 end if;
 if p_duplicate is not null then
  select f.id into v_id from public.found_items f where f.id=p_duplicate and f.is_demo=v_demo and f.status='available';
  if v_id is null then return jsonb_build_object('action','retry'); end if;
  if exists(select 1 from public.found_item_geotracks where found_item_id=v_id and tracking_scope<>v_scope) then raise exception 'Track scope mismatch'; end if;
 else
  -- Never trust a client track ID alone as proof that two photos show the same object.
  if exists(select 1 from public.found_item_geotracks where tracker_id=p_tracker) then return jsonb_build_object('action','retry'); end if;
  if exists(select 1 from public.nearby_item_geotracks(v_lat,v_lng,v_scope,v_demo,v_accuracy) n where not(n.id=any(coalesce(p_checked,'{}'::uuid[])))) then
   return jsonb_build_object('action','retry');
  end if;
  v_id:=coalesce((p_row->>'id')::uuid,gen_random_uuid()); v_created:=true;
  insert into public.found_items(id,title,description,category,color,image_path,image_paths,approximate_location,latitude,longitude,source,rover_id,status,discovered_at,is_demo)
  values(v_id,p_row->>'title',p_row->>'description',p_row->>'category',p_row->>'color',p_row->>'image_path',
   array(select jsonb_array_elements_text(coalesce(p_row->'image_paths','[]'::jsonb))),p_row->>'approximate_location',
   round(v_lat::numeric,3),round(v_lng::numeric,3),p_row->>'source',(p_row->>'rover_id')::uuid,'available',v_seen,v_demo);
 end if;
 insert into public.found_item_geotracks(found_item_id,tracker_id,tracking_scope,latitude,longitude,accuracy_m,first_seen_at,last_seen_at,sighting_count)
 values(v_id,p_tracker,v_scope,v_lat,v_lng,v_accuracy,v_seen,v_seen,case when v_created then 0 else 1 end)
 on conflict(found_item_id) do nothing;
 insert into public.found_item_geosightings(sighting_id,found_item_id,seen_at) values(p_sighting,v_id,v_seen) on conflict do nothing;
 get diagnostics v_inserted=row_count;
 if v_inserted=1 then
  update public.found_item_geotracks set last_seen_at=greatest(last_seen_at,v_seen),sighting_count=sighting_count+1 where found_item_id=v_id;
  update public.found_items f set last_seen_at=g.last_seen_at,sighting_count=g.sighting_count from public.found_item_geotracks g where f.id=v_id and g.found_item_id=f.id;
 end if;
 select * into v_result from public.found_items where id=v_id;
 return jsonb_build_object('action',case when v_created then 'created' else 'duplicate' end,'item',to_jsonb(v_result));
end;
$$;
revoke all on function public.nearby_item_geotracks(double precision,double precision,text,boolean,double precision) from public,anon,authenticated;
revoke all on function public.commit_item_geosighting(uuid,uuid,jsonb,jsonb,uuid,uuid[]) from public,anon,authenticated;
grant execute on function public.nearby_item_geotracks(double precision,double precision,text,boolean,double precision) to service_role;
grant execute on function public.commit_item_geosighting(uuid,uuid,jsonb,jsonb,uuid,uuid[]) to service_role;
