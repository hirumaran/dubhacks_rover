"""Optional, explicitly enabled operator relay to the permanent judging app."""
import json, threading, time, urllib.request
from pathlib import Path

def configure(server, repo, secret):
    server.cloud_enabled=False;server.cloud_status='off';server.cloud_deadline=0
    server.cloud_last={'webcam':0,'rover':0};server.cloud_locks={s:threading.Lock() for s in ('webcam','rover')}
    config_path=repo/'webcam/.runtime/cloud-config.json'
    server.cloud_config=json.loads(config_path.read_text()) if config_path.exists() else None
    server.cloud_secret=secret
    def watch_rover():
        import mobile
        previous=None
        while True:
            time.sleep(1)
            if not server.cloud_enabled:continue
            if time.monotonic()>server.cloud_deadline:
                server.cloud_enabled=False
                for source in ('webcam','rover'):publish(server,source=source,clear=True)
                continue
            try:
                frame=mobile.feed(server,'rover')
                if frame.get('online') and frame.get('image') and frame.get('updated_at')!=previous:
                    frame['frame_id']=int(frame['updated_at']*1000)
                    if len(frame['image'])<=400000 and publish(server,frame,'rover'):previous=frame['updated_at']
            except Exception:pass
    threading.Thread(target=watch_rover,daemon=True).start()

def publish(server, frame=None, source='webcam', clear=False):
    config=getattr(server,'cloud_config',None)
    if not config or (not clear and (not server.cloud_enabled or time.monotonic()>server.cloud_deadline)): return False
    lock=server.cloud_locks[source]
    if not clear and (time.monotonic()-server.cloud_last[source]<1 or not lock.acquire(False)):return False
    if not clear:server.cloud_last[source]=time.monotonic()
    def send():
        acquired=not clear
        try:
            if clear:
                acquired=lock.acquire(timeout=12)
                if not acquired:return
            payload={'action':'clear' if clear else 'publish','source':source}
            if frame:payload.update({key:frame[key] for key in ('image','width','height','frame_id')})
            request=urllib.request.Request(config['url']+'/functions/v1/judging-feed',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+config['anon_key'],'x-ingest-secret':server.cloud_secret},method='POST')
            with urllib.request.urlopen(request,timeout=10) as response:response.read()
            server.cloud_status='connected' if not clear else 'off'
        except Exception:server.cloud_status='reconnecting'
        finally:
            if acquired:lock.release()
    threading.Thread(target=send,daemon=True).start()
    return True
