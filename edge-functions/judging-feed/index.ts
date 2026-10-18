import { createClient } from "npm:@supabase/supabase-js@2";
import { HttpError, json, safeEqual, serve } from "../_shared/http.ts";

serve(async (body, req) => {
  const url = Deno.env.get("SUPABASE_URL")!;
  const source = body.source === "rover" ? "rover" : "webcam";
  if (body.action === "publish" || body.action === "clear") {
    const secret = Deno.env.get("ROVER_INGEST_SECRET");
    if (!secret || !safeEqual(req.headers.get("x-ingest-secret") || "",secret)) throw new HttpError(403,"Operator authentication required");
    const admin = createClient(url,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});
    if (body.action === "clear") {
      const {error}=await admin.from("judging_feeds").delete().eq("source",source); if(error)throw error;
      return json({shared:false});
    }
    if (typeof body.image !== "string" || !body.image.startsWith("data:image/jpeg;base64,") || body.image.length>400000) throw new HttpError(400,"Send a compact JPEG preview");
    const {error}=await admin.from("judging_feeds").upsert({source,image:body.image,width:body.width,height:body.height,frame_id:body.frame_id,updated_at:new Date().toISOString()});
    if(error)throw error; return json({shared:true});
  }
  const authorization=req.headers.get("Authorization");
  if(!authorization)throw new HttpError(401,"Sign in to view the judging feed");
  const client=createClient(url,Deno.env.get("SUPABASE_ANON_KEY")!,{global:{headers:{Authorization:authorization}},auth:{persistSession:false}});
  const {data:{user}}=await client.auth.getUser(authorization.replace(/^Bearer\s+/i,""));
  if(!user)throw new HttpError(401,"Sign in again");
  if(!user.is_anonymous)throw new HttpError(403,"Open Explore Demo to view the operator's judging feed");
  if(body.action==="analyze") {
    if(typeof body.image!=="string" || body.image.length>3000000)throw new HttpError(400,"Choose a smaller camera frame");
    const width=Number(body.width),height=Number(body.height);
    if(!Number.isFinite(width)||!Number.isFinite(height)||width<32||height<32)throw new HttpError(400,"Camera dimensions required");
    const start=performance.now();
    const response=await fetch(`${url}/functions/v1/identify-found-items`,{method:"POST",headers:{"Content-Type":"application/json","Authorization":authorization,"x-ingest-secret":Deno.env.get("ROVER_INGEST_SECRET")!},body:JSON.stringify({image_base64:body.image,source:"community",is_demo:true,dry_run:true,latitude:0,longitude:0,approximate_location:"Judging demo camera — no location collected",min_box_px:32})});
    const result=await response.json();if(!response.ok)throw new HttpError(502,"Camera recognition is unavailable. Please retry.");
    // The existing identifier reports pixel boxes; map into the app's normalized format.
    return json({width,height,dry_run:true,model:"Perceptron Mk1.5",elapsed_s:Math.round((performance.now()-start)/10)/100,skipped_count:result.skipped?.length||0,detections:(result.identified||[]).map((item:Record<string,unknown>)=>{const b=item.box as {x1:number;y1:number;x2:number;y2:number};return {...item,bbox:[b.x1/width,b.y1/height,(b.x2-b.x1)/width,(b.y2-b.y1)/height]};})});
  }
  const {data,error}=await client.from("judging_feeds").select("*").eq("source",source).maybeSingle();if(error)throw error;
  if(!data)return json({source,online:false,image:null,detections:[],analysis:null});
  return json({...data,updated_at:Date.parse(data.updated_at)/1000,online:true,detections:[],analysis:null});
});
