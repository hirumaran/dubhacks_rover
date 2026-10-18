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
def child(args, **kwargs):
    p=subprocess.Popen(args,start_new_session=(os.name=='posix'),**kwargs);processes.append(p);return p
try:
    deno=[shutil.which('deno')] if shutil.which('deno') else ['npx','--yes','deno@2.9.6']
    model=child(deno+['run','--node-modules-dir=none','--allow-net','--allow-env',str(REPO/'edge-functions/identify-found-items/index.ts')],cwd=REPO,env=env)
    for _ in range(120):
        if not available(8001): break
        if model.poll() is not None: sys.exit('Identification service could not start.')
        time.sleep(.25)
    else: sys.exit('Identification service timed out while starting.')
    web=child([sys.executable,str(ROOT/'server.py')],cwd=REPO,env={**os.environ,'WEBCAM_IDENTIFY_PORT':'8001'})
    print('\nOpen http://127.0.0.1:8769/ in Chrome, then choose Enable webcam.\nCtrl+C stops this demo. Microphone and database uploads stay disabled.\n',flush=True)
    while web.poll() is None and model.poll() is None: time.sleep(.5)
except KeyboardInterrupt: pass
finally:
    for p in reversed(processes):
        if p.poll() is None:
            if os.name=='posix': os.killpg(p.pid,signal.SIGTERM)
            else: p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name=='posix': os.killpg(p.pid,signal.SIGKILL)
                else: p.kill()
