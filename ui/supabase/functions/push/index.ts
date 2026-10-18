// Database webhook target for INSERT on notifications. Configure PUSH_WEBHOOK_SECRET
// as an x-webhook-secret header; deploy with --no-verify-jwt for this webhook only.
import { createClient } from 'npm:@supabase/supabase-js@2';
Deno.serve(async (req:Request)=>{
 const secret=Deno.env.get('PUSH_WEBHOOK_SECRET');
 if(!secret||req.headers.get('x-webhook-secret')!==secret)return new Response('Unauthorized',{status:401});
 const db=createClient(Deno.env.get('SUPABASE_URL')!,Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
 const payload=await req.json();if(payload.type!=='INSERT'||payload.table!=='notifications')return new Response('Ignored');
 // Read the canonical record; never trust supplied user IDs or notification text.
 const {data:n,error}=await db.from('notifications').select('*').eq('id',payload.record?.id).single();
 if(error)return new Response('Unknown notification',{status:400});
 const {data:p}=await db.from('profiles').select('notifications_enabled').eq('id',n.user_id).single();
 if(!p?.notifications_enabled)return new Response('Disabled');
 const {data:tokens,error:tokenError}=await db.from('push_tokens').select('token').eq('user_id',n.user_id);
 if(tokenError)return new Response('Token lookup failed',{status:500});
 if(!tokens?.length)return new Response('No registered device');
 const response=await fetch('https://exp.host/--/api/v2/push/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(tokens.map(t=>({to:t.token,sound:'default',title:n.title,body:n.message,data:{itemId:n.related_item_id,reportId:n.related_report_id,notificationId:n.id}})))});
 return new Response(await response.text(),{status:response.status,headers:{'Content-Type':'application/json'}});
});
