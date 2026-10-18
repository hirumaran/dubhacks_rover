-- A consented demo camera keeps only its latest frame; expired frames are not readable.
create table public.judging_feeds (
 source text primary key check(source in ('webcam','rover')),
 image text not null check(octet_length(image)<=400000),
 width integer not null check(width between 32 and 1280),
 height integer not null check(height between 32 and 960),
 frame_id bigint not null,
 updated_at timestamptz not null default now()
);
alter table public.judging_feeds enable row level security;
revoke all on public.judging_feeds from anon,authenticated;
grant select on public.judging_feeds to authenticated;
create policy demo_live_read on public.judging_feeds for select to authenticated using(
 coalesce((auth.jwt()->>'is_anonymous')::boolean,false) and updated_at>now()-interval '15 seconds'
);
