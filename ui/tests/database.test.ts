import { PGlite } from "@electric-sql/pglite";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";

test("migrations, server matching, and cross-account RLS boundaries", async () => {
  const db = new PGlite();
  try {
    await db.exec(`
 create role anon; create role authenticated;
 create schema auth; create schema storage;
 create table auth.users(id uuid primary key,email text,raw_user_meta_data jsonb default '{}',is_anonymous boolean default false);
 create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
 create function auth.jwt() returns jsonb language sql stable as $$ select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb $$;
 create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
 create table storage.objects(id uuid default gen_random_uuid(),bucket_id text,name text);
 alter table storage.objects enable row level security;
 create function storage.foldername(text) returns text[] language sql as $$ select string_to_array($1,'/') $$;
 grant usage on schema public,auth,storage to authenticated;
 alter default privileges in schema public grant all on tables to authenticated;
 grant all on storage.objects to authenticated;
 create publication supabase_realtime;
 `);
    const schema = readFileSync(
      "supabase/migrations/202610170001_huskyfind.sql",
      "utf8",
    ).replace("create extension if not exists pgcrypto;", "");
    await db.exec(schema);
    await db.exec(
      readFileSync("supabase/migrations/202610170002_demo.sql", "utf8"),
    );
    await db.exec(
      readFileSync(
        "supabase/migrations/202610170003_demo_boundaries.sql",
        "utf8",
      ),
    );
    const a = "20000000-0000-0000-0000-000000000001",
      b = "20000000-0000-0000-0000-000000000002";
    await db.exec(
      `insert into auth.users(id,is_anonymous) values('${a}',true),('${b}',true);`,
    );
    async function asUser(id: string, reviewer = false) {
      await db.exec(
        `reset role;set role authenticated;select set_config('request.jwt.claim.sub','${id}',false);select set_config('request.jwt.claims','{"is_anonymous":true,"app_metadata":{"role":"${reviewer ? "reviewer" : "student"}"}}',false);`,
      );
    }
    await asUser(a);
    await db.exec(
      "select public.initialize_demo();select public.initialize_demo();",
    );
    let rows = await db.query("select * from public.missing_reports");
    assert.equal(rows.rows.length, 1, "demo initialization is idempotent");
    const matches = await db.query<{ id: string }>(
      "select id from public.item_matches",
    );
    assert.ok(matches.rows.length >= 1, "server creates a match");
    const notifications = await db.query("select * from public.notifications");
    assert.ok(notifications.rows.length >= 1, "server creates a notification");
    await assert.rejects(
      db.exec(`update public.profiles set university_verified=true`),
      /permission denied/,
    );
    await assert.rejects(
      db.exec(`update public.item_matches set match_score=100`),
      /permission denied/,
    );
    await db.exec(
      `update public.item_matches set status='dismissed' where id='${matches.rows[0].id}'`,
    );
    const forbiddenUpdate = await db.query(
      `update public.claims set status='approved' returning *`,
    );
    assert.equal(
      forbiddenUpdate.rows.length,
      0,
      "students cannot approve claims",
    );
    await assert.rejects(
      db.exec(
        `insert into public.found_items(title,description,category,color,image_path,approximate_location,latitude,longitude,source) values('fake','fake','Keys','Black','x','x',47,-122,'rover')`,
      ),
      /row-level security/,
    );
    await asUser(b);
    for (const table of [
      "missing_reports",
      "claims",
      "search_requests",
      "item_matches",
      "notifications",
      "profiles",
    ]) {
      const result = await db.query(`select * from public.${table}`);
      assert.equal(
        result.rows.length,
        table === "profiles" ? 1 : 0,
        `${table} hides other students' data`,
      );
    }
    await assert.rejects(
      db.exec(`select public.recheck_report('${a}')`),
      /permission denied/,
    );
    await asUser(b, true);
    const claims = await db.query<{ id: string }>(
      "select id from public.claims",
    );
    assert.equal(claims.rows.length, 1, "reviewers see claims");
    await db.exec(
      `update public.claims set status='approved' where id='${claims.rows[0].id}'`,
    );
    await asUser(a);
    const updated = await db.query<{ status: string }>(
      "select status from public.claims",
    );
    assert.equal(updated.rows[0].status, "approved");
    await db.exec("select public.delete_my_account()");
    await db.exec("reset role");
    const remaining = await db.query(
      `select * from public.missing_reports where user_id='${a}'`,
    );
    assert.equal(
      remaining.rows.length,
      0,
      "account deletion cascades private reports",
    );
  } finally {
    await db.close();
  }
});
