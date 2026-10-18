insert into public.found_items(id,title,description,category,color,image_path,approximate_location,latitude,longitude,source,is_demo,discovered_at) values
('10000000-0000-0000-0000-000000000001','Black insulated bottle','Black insulated water bottle with a silver lid.','Water Bottles','Black','https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=700&fit=crop','Odegaard Library',47.6566,-122.3102,'rover',true,now()-interval '12 minutes'),
('10000000-0000-0000-0000-000000000002','Everyday backpack','A canvas backpack left by the seating area.','Bags','Brown','https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=700&fit=crop','Husky Union Building',47.6553,-122.3051,'community',true,now()-interval '45 minutes'),
('10000000-0000-0000-0000-000000000003','Wireless headphones','Over-ear headphones with padded ear cushions.','Electronics','Black','https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=700&fit=crop','Suzzallo Library',47.6558,-122.308,'community',true,now()-interval '2 hours'),
('10000000-0000-0000-0000-000000000004','A set of keys','House keys on a small metal key ring.','Keys','Silver','https://images.unsplash.com/photo-1582139329536-e7284fece509?w=700&fit=crop','Red Square',47.6559,-122.3093,'rover',true,now()-interval '3 hours'),
('10000000-0000-0000-0000-000000000005','Compact camera','Small camera with a black strap.','Electronics','Black','https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=700&fit=crop','IMA',47.6536,-122.301,'community',true,now()-interval '5 hours');
create function public.initialize_demo() returns void language plpgsql security definer set search_path='' as $$ declare r uuid; begin
if auth.uid() is null or not coalesce((auth.jwt()->>'is_anonymous')::boolean,false) then raise exception 'Demo accounts only'; end if;
perform pg_advisory_xact_lock(hashtext(auth.uid()::text));
if exists(select 1 from public.missing_reports where user_id=auth.uid()) then return; end if;
insert into public.missing_reports(user_id,title,description,category,color,last_seen_location,latitude,longitude,last_seen_at) values(auth.uid(),'My black water bottle (demo)','Black insulated water bottle with silver lid','Water Bottles','Black','Odegaard Library',47.6566,-122.3102,now()-interval '1 day') returning id into r;
insert into public.search_requests(user_id,missing_report_id,target_location) values(auth.uid(),r,'Odegaard Library (demo)');
insert into public.claims(user_id,found_item_id,verification_details) values(auth.uid(),'10000000-0000-0000-0000-000000000003','{"features":"Sample demo evidence: initials inside the headband","where_and_when":"Suzzallo yesterday — demo only"}');
end $$;
revoke all on function public.initialize_demo() from public,anon;
grant execute on function public.initialize_demo() to authenticated;
