#!/usr/bin/env python3
"""Start the webcam gateway and a separate, forced-dry-run Perceptron identifier."""
from pathlib import Path
import os, sys, shutil, signal, socket, subprocess, time
from server import read_env
ROOT=Path(__file__).resolve().parent; REPO=ROOT.parent
processes=[]
def available(port):
    with socket.socket() as s: return s.connect_ex(('127.0.0.1',port)) != 0
for port in (8769,8001):
    if not available(port): sys.exit(f'Port {port} is in use. Close the existing webcam demo first.')
keys=read_env(REPO/'edge-functions/.env'); ui=read_env(REPO/'ui/.env')
if not keys.get('PERCEPTRON_API_KEY') or not keys.get('ROVER_INGEST_SECRET'):
    sys.exit('Configure PERCEPTRON_API_KEY and ROVER_INGEST_SECRET in private edge-functions/.env first.')
# Dry-run returns before any database queries. These values only initialize the shared client.
env={**os.environ,**keys,'LOCAL_ONLY':'1','PORT':'8001',
     'SUPABASE_URL':ui.get('EXPO_PUBLIC_SUPABASE_URL','https://webcam-unused.invalid'),
     'SUPABASE_SERVICE_ROLE_KEY':ui.get('EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY','webcam-dry-run-unused')}
# Deno moves downloaded files atomically. Keep its temp/cache on the same drive
# as the project on Windows instead of mixing the system C: temp with D:.
runtime=ROOT/'.runtime'; temporary=runtime/'tmp'
temporary.mkdir(parents=True,exist_ok=True)
env.update({'DENO_DIR':str(runtime/'deno'),'TEMP':str(temporary),'TMP':str(temporary),'TMPDIR':str(temporary)})
def child(args, **kwargs):
    p=subprocess.Popen(args,start_new_session=(os.name=='posix'),**kwargs);processes.append(p);return p
try:
    deno=[shutil.which('deno')] if shutil.which('deno') else [shutil.which('npx.cmd' if os.name=='nt' else 'npx') or 'npx','--yes','deno@2.9.6']
    model=child(deno+['run','--node-modules-dir=none','--allow-net','--allow-env',str(REPO/'edge-functions/identify-found-items/index.ts')],cwd=REPO,env=env)
    for _ in range(360):
        if not available(8001): break
        if model.poll() is not None: sys.exit('Identification service could not start.')
        time.sleep(.25)
    else: sys.exit('Identification service timed out while starting.')
    web=child([sys.executable,str(ROOT/'server.py')],cwd=REPO,env={**os.environ,'WEBCAM_IDENTIFY_PORT':'8001','WEBCAM_MOBILE':'1' if '--mobile' in sys.argv else '0'})
    for _ in range(100):
        if not available(8769): break
        if web.poll() is not None: sys.exit('Scout gateway could not start.')
        time.sleep(.1)
    else: sys.exit('Scout gateway timed out while starting.')
    print('\nOpen http://127.0.0.1:8769/ in Chrome, then choose Enable webcam.\nCtrl+C stops this demo. Microphone and database uploads stay disabled.\n',flush=True)
    if '--mobile' in sys.argv and '--no-open' not in sys.argv:
        # Camera permission still requires the user's Enable webcam click.
        import webbrowser
        try: webbrowser.open('http://127.0.0.1:8769/')
        except Exception: pass
    while web.poll() is None and model.poll() is None: time.sleep(.5)
except KeyboardInterrupt: pass
finally:
    for p in reversed(processes):
        if p.poll() is None:
            if os.name=='posix': os.killpg(p.pid,signal.SIGTERM)
            else:
                # npx starts Deno as a descendant. Stop the owned process tree so
                # the model cannot retain port 8001 after the launcher exits.
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name=='posix': os.killpg(p.pid,signal.SIGKILL)
                else: p.kill()
