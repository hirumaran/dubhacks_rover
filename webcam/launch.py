#!/usr/bin/env python3
"""Start the webcam gateway and a separate, forced-dry-run Perceptron identifier."""
from pathlib import Path
import os, sys, shutil, signal, socket, subprocess, time, json, urllib.request
from server import read_env
ROOT=Path(__file__).resolve().parent; REPO=ROOT.parent
processes=[]
def available(port):
    with socket.socket() as s: return s.connect_ex(('127.0.0.1',port)) != 0
if not available(8769):
    # A previous terminal or Codex session may still own the healthy gateway.
    # Recognize our service instead of starting another model or killing a port owner.
    try:
        with urllib.request.urlopen('http://127.0.0.1:8769/api/config', timeout=3) as response:
            existing = json.load(response)
        if existing.get('model') != 'Perceptron Mk1.5' or existing.get('dry_run') is not True or not existing.get('token'):
            raise ValueError('Not a HuskyFind gateway')
    except Exception:
        sys.exit('Port 8769 belongs to another service or an unresponsive gateway. Close that service, then retry.')
    print('HuskyFind Scout is already running in the background. Reusing it.\n'
          'Open http://127.0.0.1:8769/ and choose Enable webcam, then Share with judging link.\n'
          'Judges use the same permanent app QR; another gateway is not needed.', flush=True)
    if '--mobile' in sys.argv:
        try:
            request = urllib.request.Request('http://127.0.0.1:8769/api/pairing', data=b'{}',
                headers={'Content-Type':'application/json','X-Webcam-Token':existing['token']}, method='POST')
            with urllib.request.urlopen(request, timeout=3) as response:
                pairing = json.load(response)
            print(f'\nSCOUT PAIRING CODE: {pairing["code"]}\nPaste this code into Expo Go > Scout > Connect to Scout.\n', flush=True)
        except Exception:
            print('The running gateway is an older version. Restart its launch terminal once to enable pairing-code recovery.', flush=True)
    if '--mobile' in sys.argv and '--no-open' not in sys.argv:
        import webbrowser
        try: webbrowser.open('http://127.0.0.1:8769/')
        except Exception: pass
    sys.exit(0)
if not available(8001):
    sys.exit('Port 8001 is already in use, but the camera gateway is not running. Close the existing model service, then retry.')
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
