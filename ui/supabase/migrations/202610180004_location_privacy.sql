-- Preserve server-side coordinates while preventing discovery GPS reads by clients.
revoke select on public.found_items from public,anon,authenticated;
grant select (id,title,description,category,color,image_path,image_paths,approximate_location,source,rover_id,status,pickup_location,discovered_at,created_at,is_demo) on public.found_items to authenticated;
-- Realtime broadcasts full discovery rows; private report/search subscriptions remain active.
alter publication supabase_realtime drop table public.found_items;
