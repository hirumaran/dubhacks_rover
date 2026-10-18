import type {Rating} from './rating.ts';
export type ItemGeo={latitude:number;longitude:number;accuracy_m:number;scope:string;tracker_id:string;sighting_id:string};
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function parseItemGeo(v:unknown):ItemGeo|null{
 if(v===undefined||v===null)return null;
 if(typeof v!=='object'||Array.isArray(v))throw Error('item_location must be an object');
 const g=v as ItemGeo;
 if(!Number.isFinite(g.latitude)||g.latitude < -90||g.latitude>90||!Number.isFinite(g.longitude)||g.longitude < -180||g.longitude>180||!Number.isFinite(g.accuracy_m)||g.accuracy_m<.1||g.accuracy_m>25||typeof g.scope!=='string'||!g.scope.trim()||g.scope.length>160||!UUID.test(g.tracker_id)||!UUID.test(g.sighting_id))throw Error('Invalid item_location coordinates, accuracy, scope or UUIDs');
 return {...g,scope:g.scope.trim()};
}
export function samePhysicalItem(r:Rating):boolean{return r.verdict==='same_item'&&r.similarity>=85;}
export function uncertainIdentity(r:Rating):boolean{return !samePhysicalItem(r)&&r.verdict!=='different'&&r.verdict!=='likely_different';}

export function identityKind(title:string):string|null {
 const words=title.toLowerCase().match(/[a-z]+/g)??[];
 const aliases:Record<string,string>={rucksack:'backpack',knapsack:'backpack',macbook:'laptop',computer:'laptop',flask:'bottle',tumbler:'bottle',textbook:'book',notebook:'book',smartphone:'phone'};
 const kinds=new Set('backpack laptop bottle book phone wallet keys umbrella headphones glasses bag jacket hat calculator watch purse'.split(' '));
 return words.map(w=>aliases[w]??w).find(w=>kinds.has(w))??null;
}
export function closeAnchorConflict(a:{title:string;category:string},b:{title:string;category:string},distance:number):boolean {
 const ak=identityKind(a.title),bk=identityKind(b.title);
 return distance<=1&&(ak&&bk?ak===bk:a.category===b.category);
}
