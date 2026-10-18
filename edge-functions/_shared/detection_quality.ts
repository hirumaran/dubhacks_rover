/** Pure, deterministic rejection gates; no model-generated confidence is treated as proof. */
export type PixelBox = {x1:number;y1:number;x2:number;y2:number};
const GENERIC = new Set('a an the small large big tiny dark light colored rectangular rectangle round square cylindrical flat object objects item items thing personal portable belonging belongings unknown unclear unidentifiable other unidentified plastic metal rubber leather fabric wooden shape solid smooth surface edge black white red blue green yellow orange purple brown gray grey silver gold pink teal clear transparent multicolor'.split(' '));
const FIXTURES = new Set('bench benches slat slats armrest backrest furniture chair table desk wall building ground floor tile pavement path railing column pillar tree plant planter bin trashcan sign fixture'.split(' '));
export function geometryReason(box:PixelBox,width:number,height:number,minLong=0):string|null{
 const {x1,y1,x2,y2}=box;const w=x2-x1,h=y2-y1;
 if(![x1,y1,x2,y2].every(Number.isFinite)||x1<0||y1<0||x2>width||y2>height||w<12||h<12||Math.max(w,h)<minLong)return 'small, clipped or invalid detection box';
 if(w*h/(width*height)>.35)return 'box covers too much of the scene';
 return null;
}
export function specificIdentity(value:string):boolean{
 const words=value.toLowerCase().split(/\b(?:on|near|beside|under|next to|sitting|resting|lying)\b/)[0].match(/[a-z]+/g)??[];
 return !words.some(w=>FIXTURES.has(w))&&words.some(w=>w.length>2&&!GENERIC.has(w));
}
export function blankPixels(bitmap:Uint8Array|Uint8ClampedArray):boolean{
 let n=0,total=0,squares=0,black=0;const step=Math.max(4,Math.floor(bitmap.length/(4*4096))*4);
 for(let i=0;i<bitmap.length;i+=step){const v=(bitmap[i]+bitmap[i+1]+bitmap[i+2])/3;n++;total+=v;squares+=v*v;if(v<8)black++;}
 return n===0||Math.sqrt(Math.max(0,squares/n-(total/n)**2))<2||black/n>.995;
}
