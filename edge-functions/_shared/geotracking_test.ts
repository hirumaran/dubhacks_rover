import {parseItemGeo,samePhysicalItem,uncertainIdentity,closeAnchorConflict} from './geotracking.ts';
import type {Rating} from './rating.ts';
const assert=(v:unknown)=>{if(!v)throw Error('Assertion failed');};
const geo={latitude:47.65,longitude:-122.30,accuracy_m:2,scope:'gates-floor-1',tracker_id:'11111111-1111-4111-8111-111111111111',sighting_id:'22222222-2222-4222-8222-222222222222'};
Deno.test('precise location metadata validates without exposing it in public data',()=>{assert(parseItemGeo(geo)?.scope===geo.scope);assert(parseItemGeo(undefined)===null);for(const bad of [{...geo,latitude:NaN},{...geo,longitude:181},{...geo,accuracy_m:0},{...geo,scope:''},{...geo,tracker_id:'not-a-uuid'}]){let failed=false;try{parseItemGeo(bad);}catch{failed=true;}assert(failed);}});
Deno.test('location proximity and a high score alone do not establish physical identity',()=>{const r={similarity:99,verdict:'likely_same',matching_features:['black'],differences:[],summary:''}as Rating;assert(!samePhysicalItem(r));assert(uncertainIdentity(r));assert(samePhysicalItem({...r,verdict:'same_item'}));assert(!uncertainIdentity({...r,verdict:'different'}));});

Deno.test('one-meter conflicting anchor is deferred, but a different kind can coexist',()=>{assert(closeAnchorConflict({title:'Black backpack',category:'Bags'},{title:'Brown backpack',category:'Bags'},.2));assert(!closeAnchorConflict({title:'Backpack',category:'Bags'},{title:'Laptop',category:'Electronics'},.2));assert(!closeAnchorConflict({title:'Backpack',category:'Bags'},{title:'Backpack',category:'Bags'},2));});
