import {geometryReason,specificIdentity,blankPixels} from './detection_quality.ts';
function ok(v:unknown){if(!v)throw Error('assertion failed');}
Deno.test('reject whole-scene hallucination and invalid geometry',()=>{
 ok(geometryReason({x1:0,y1:0,x2:640,y2:480},640,480));
 ok(geometryReason({x1:-2,y1:10,x2:80,y2:90},640,480));
 ok(geometryReason({x1:NaN,y1:10,x2:80,y2:90},640,480));
 ok(!geometryReason({x1:100,y1:100,x2:180,y2:240},640,480,48));
});
Deno.test('blank controls cannot reach the model',()=>{
 ok(blankPixels(new Uint8Array(64*64*4)));
 ok(blankPixels(new Uint8Array(64*64*4).fill(255)));
 const px=new Uint8Array(64*64*4);for(let i=0;i<px.length;i++)px[i]=Math.floor(i/4)%251;
 ok(!blankPixels(px));
});
Deno.test('specific types required; structural and generic objects rejected',()=>{
 for(const t of ['Other','Small black rectangular object','portable personal belonging','bench slat','wall panel'])ok(!specificIdentity(t));
 for(const t of ['backpack','laptop','water bottle','umbrella','rubber duck'])ok(specificIdentity(t));
});
