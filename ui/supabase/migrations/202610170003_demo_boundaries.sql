-- Dispatchers must explicitly filter is_demo=false before assigning physical rovers.
alter table public.missing_reports add column is_demo boolean not null default coalesce((auth.jwt()->>'is_anonymous')::boolean,false);
alter table public.search_requests add column is_demo boolean not null default coalesce((auth.jwt()->>'is_anonymous')::boolean,false);
alter table public.claims add column is_demo boolean not null default coalesce((auth.jwt()->>'is_anonymous')::boolean,false);
update public.missing_reports m set is_demo=coalesce(u.is_anonymous,false) from auth.users u where u.id=m.user_id;
update public.search_requests m set is_demo=coalesce(u.is_anonymous,false) from auth.users u where u.id=m.user_id;
update public.claims m set is_demo=coalesce(u.is_anonymous,false) from auth.users u where u.id=m.user_id;
create function public.enforce_demo_boundary() returns trigger language plpgsql security definer set search_path='' as $$ begin
select coalesce(is_anonymous,false) into new.is_demo from auth.users where id=new.user_id;
return new; end $$;
create trigger report_demo_boundary before insert or update on public.missing_reports for each row execute function public.enforce_demo_boundary();
create trigger search_demo_boundary before insert or update on public.search_requests for each row execute function public.enforce_demo_boundary();
create trigger claim_demo_boundary before insert or update on public.claims for each row execute function public.enforce_demo_boundary();
create function public.notify_pickup() returns trigger language plpgsql security definer set search_path='' as $$ begin
if new.pickup_location is not null and new.pickup_location is distinct from old.pickup_location then
insert into public.notifications(user_id,title,message,related_item_id) select user_id,'Item ready for pickup',new.title || ' · ' || new.pickup_location,new.id from public.claims where found_item_id=new.id and status='approved';
end if; return new; end $$;
create trigger pickup_notification after update on public.found_items for each row execute function public.notify_pickup();
