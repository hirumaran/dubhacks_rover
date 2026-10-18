import {PGlite} from '@electric-sql/pglite';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {test} from 'node:test';
const uuid=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
test('private geo inventory: retries, repeated sightings, races and access boundaries',async()=>{
 const db=new PGlite();try{
  await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;
   create table public.found_items(id uuid primary key,title text not null,description text not null,category text not null,color text not null,image_path text not null,image_paths text[],approximate_location text,latitude double precision,longitude double precision,source text,rover_id uuid,status text,discovered_at timestamptz,is_demo boolean);
   grant usage on schema public to anon,authenticated,service_role;alter default privileges in schema public grant all on tables to authenticated;`);
  await db.exec(readFileSync('supabase/migrations/202610170004_item_geotracking.sql','utf8'));
  const geo={latitude:47.652901,longitude:-122.304501,accuracy_m:2,scope:'gates-floor-1'};
  const row={id:uuid(1),title:'Black backpack',description:'Backpack with yellow buckles',category:'Bags',color:'Black',image_path:'photo.jpg',image_paths:[],approximate_location:'Gates',source:'rover',rover_id:null,discovered_at:'2026-10-18T04:00:00Z',is_demo:true};
  async function commit(sighting:number,tracker:number,r= row,g=geo,duplicate:string|null=null,checked:string[]=[]){return (await db.query<{result:any}>('select public.commit_item_geosighting($1,$2,$3::jsonb,$4::jsonb,$5,$6::uuid[]) as result',[uuid(sighting),uuid(tracker),JSON.stringify(r),JSON.stringify(g),duplicate,checked])).rows[0].result;}
  assert.equal((await commit(10,20)).action,'created');
  assert.equal((await commit(10,20)).idempotent,true);
  let items=await db.query<{sighting_count:number;latitude:number}>('select * from found_items');assert.equal(items.rows.length,1);assert.equal(items.rows[0].sighting_count,1);assert.equal(items.rows[0].latitude,47.653,'public location stays approximate');
  assert.equal((await commit(11,21,{...row,id:uuid(2)})).action,'retry','a concurrently inserted unchecked neighbor forces re-comparison');
  assert.equal((await commit(11,21,{...row,id:uuid(2)},geo,uuid(1),[uuid(1)])).action,'duplicate');
  items=await db.query('select * from found_items');assert.equal(items.rows.length,1);assert.equal(items.rows[0].sighting_count,2);
  assert.equal((await commit(12,22,{...row,id:uuid(3),title:'Laptop',category:'Electronics'},geo,null,[uuid(1)])).action,'created','visually different co-located items remain separate');
  const candidates=await db.query('select * from public.nearby_item_geotracks($1,$2,$3,$4,$5)',[geo.latitude,geo.longitude,geo.scope,true,2]);assert.equal(candidates.rows.length,2);
  const later={...row,id:uuid(9),discovered_at:'2026-10-21T04:00:00Z'};
  assert.equal((await commit(14,24,later,geo,uuid(1),[uuid(1),uuid(3)])).action,'duplicate','items persist beyond the previous 24-hour dedup window');
  assert.equal((await db.query('select * from public.nearby_item_geotracks($1,$2,$3,$4,$5)',[geo.latitude,geo.longitude,'other-floor',true,2])).rows.length,0);
  assert.equal((await db.query('select * from public.nearby_item_geotracks($1,$2,$3,$4,$5)',[geo.latitude,geo.longitude,geo.scope,false,2])).rows.length,0);
  await db.exec("update found_items set status='returned' where id='"+uuid(1)+"'");
  assert.equal((await db.query('select * from public.nearby_item_geotracks($1,$2,$3,$4,$5)',[geo.latitude,geo.longitude,geo.scope,true,2])).rows.length,1,'returned items are not candidates');
  await db.exec('set role authenticated');
  await assert.rejects(db.query('select * from public.found_item_geotracks'),/permission denied/);
  await assert.rejects(db.query('select * from public.found_item_geosightings'),/permission denied/);
  await assert.rejects(db.query('select * from public.nearby_item_geotracks($1,$2,$3,$4,$5)',[geo.latitude,geo.longitude,geo.scope,true,2]),/permission denied/);
  await db.exec('reset role;set role anon');
  await assert.rejects(db.query('select * from public.found_item_geotracks'),/permission denied/);
 }finally{await db.close();}
});
