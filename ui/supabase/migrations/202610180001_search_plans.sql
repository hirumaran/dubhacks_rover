-- Cloud search planning; demo fleet assignments never command a physical rover.
alter table public.rovers add column latitude double precision;
alter table public.rovers add column longitude double precision;
alter table public.rovers add column is_demo boolean not null default false;
alter table public.search_requests add column search_brief jsonb;
alter table public.search_requests add column assignment_reason text;
alter table public.search_requests add column assignment_distance_m integer;
insert into public.rovers(id,name,status,operating_zone,latitude,longitude,is_demo) values
('57000000-0000-0000-0000-000000000001','Scout · Red Square','available','Red Square / Odegaard',47.6560,-122.3095,true),
('57000000-0000-0000-0000-000000000002','Scout · The Quad','available','Suzzallo / The Quad',47.6561,-122.3075,true),
('57000000-0000-0000-0000-000000000003','Scout · HUB','available','HUB / IMA',47.6548,-122.3037,true);

create or replace function public.plan_rover_search(report_id uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare r public.missing_reports; request public.search_requests; rover public.rovers;
demo boolean; distance_m integer; reason text; brief jsonb;
begin
 if auth.uid() is null then raise exception 'Sign in to plan a search'; end if;
 select * into r from public.missing_reports where id=report_id and user_id=auth.uid() for update;
 if not found then raise exception 'Report not found'; end if;
 if r.status<>'active' then raise exception 'Only active reports can request a search'; end if;
 select coalesce(is_anonymous,false) into demo from auth.users where id=auth.uid();
 select * into request from public.search_requests where missing_report_id=r.id;
 if request.rover_id is not null then
   select * into rover from public.rovers where id=request.rover_id;
   return jsonb_build_object('request_id',request.id,'rover_id',rover.id,'rover_name',rover.name,'status',request.status,'demo',demo,'reason',request.assignment_reason,'distance_m',request.assignment_distance_m,'brief',request.search_brief);
 end if;
 select v.* into rover from public.rovers v
 where v.is_demo=demo and v.status in ('available','idle','patrolling') and v.latitude is not null and v.longitude is not null
 and (demo or v.last_seen_at>now()-interval '2 minutes')
 and (demo or not exists(select 1 from public.search_requests q where q.rover_id=v.id and q.status in ('assigned','searching')))
 order by power((v.latitude-r.latitude)*111320,2)+power((v.longitude-r.longitude)*75000,2), v.id
 limit 1 for update skip locked;
 if rover.id is not null then
   distance_m:=round(sqrt(power((rover.latitude-r.latitude)*111320,2)+power((rover.longitude-r.longitude)*75000,2)));
   reason:='Closest available '||case when demo then 'demo rover' else 'online rover' end||' to '||r.last_seen_location||' ('||distance_m||' m straight-line estimate).';
 else reason:='No eligible online rover is available. Request stays queued until campus operations assigns one.';
 end if;
 brief:=jsonb_build_object('target',r.title,'category',r.category,'color',r.color,'visual_cues',r.description,'search_area',r.last_seen_location,'latitude',r.latitude,'longitude',r.longitude,'reference_photo_path',r.image_path,'last_seen_at',r.last_seen_at,
 'matching_weights',jsonb_build_object('category',35,'color',20,'location',20,'appearance',15,'time',10),
 'instruction','Look for the visible shape, color, material and distinguishing features in the reference photo. Re-observe from another viewpoint before identifying an item. Never infer ownership from appearance alone.');
 insert into public.search_requests(user_id,missing_report_id,target_location,rover_id,status,search_brief,assignment_reason,assignment_distance_m)
 values(auth.uid(),r.id,r.last_seen_location,rover.id,case when rover.id is null then 'queued' else 'assigned' end,brief,reason,distance_m)
 on conflict(missing_report_id) do update set rover_id=excluded.rover_id,status=excluded.status,search_brief=excluded.search_brief,assignment_reason=excluded.assignment_reason,assignment_distance_m=excluded.assignment_distance_m
 returning * into request;
 return jsonb_build_object('request_id',request.id,'rover_id',rover.id,'rover_name',rover.name,'status',request.status,'demo',demo,'reason',reason,'distance_m',distance_m,'brief',brief);
end $$;
revoke all on function public.plan_rover_search(uuid) from public,anon;
grant execute on function public.plan_rover_search(uuid) to authenticated;
