const types=['backpack','laptop','bottle','book','phone','wallet','keys','umbrella','headphones','glasses','bag','jacket','hat','calculator','watch','purse'];
function type(item){const s=(item.title||item.object_type||'').toLowerCase().split(/\b(?:on|near|beside|under|with)\b/)[0];return types.find(t=>new RegExp('\\b'+t+'s?\\b').test(s))||s.replace(/\b(black|white|blue|red|green|yellow|small|large|the|a)\b/g,'').trim();}
function iou(a,b){const [x,y,w,h]=a,[u,v,r,s]=b;const overlap=Math.max(0,Math.min(x+w,u+r)-Math.max(x,u))*Math.max(0,Math.min(y+h,v+s)-Math.max(y,v));return overlap/(w*h+r*s-overlap||1);}
export class RepeatTracker{
 constructor(){this.seq=0;this.next=0;this.tracks=[];}
 update(items){this.seq++;const used=new Set();this.tracks=this.tracks.filter(t=>t.last>=this.seq-2);return items.map(item=>{
   const kind=type(item);let track=this.tracks.find(t=>!used.has(t.id)&&t.kind===kind&&t.last===this.seq-1&&iou(t.bbox,item.bbox)>.25&&(!t.color||!item.color||t.color===item.color));
   if(track){track.streak++;track.last=this.seq;track.bbox=item.bbox;}else{track={id:++this.next,kind,last:this.seq,streak:1,bbox:item.bbox,color:item.color};this.tracks.push(track);}
   used.add(track.id);return {...item,track_id:track.id,consecutive_scans:track.streak,repeated:track.streak>=2};
 });}
}
