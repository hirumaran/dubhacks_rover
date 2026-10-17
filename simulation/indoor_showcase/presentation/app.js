const $ = id => document.getElementById(id);
let previousScan = null, previousTime = 0, lastGallery = '', lastHistory = '', posting = false, displayedScan = null, pinnedScan = false;
const titles = {backpack: 'Backpack', book: 'Book', bottle: 'Water bottle'};
const itemCount = n => n + (n === 1 ? ' item' : ' items');
const clock = t => String(Math.floor(t / 60)).padStart(2, '0') + ':' + String(Math.floor(t % 60)).padStart(2, '0');
function toast(message) {
  $('toast').textContent = message; $('toast').classList.add('visible');
  setTimeout(() => $('toast').classList.remove('visible'), 2600);
}
async function command(body) {
  try {
    const res = await fetch('/api/control', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    if (res.status === 409) { toast('Start Webots to use live camera controls.'); return false; }
    if (!res.ok) throw Error(); return true;
  } catch { toast('The local showcase server is unavailable.'); return false; }
}
document.querySelectorAll('[data-view]').forEach(b => b.onclick = async () => {
  if (await command({view: b.dataset.view})) toast('Camera changed to ' + b.textContent.trim());
});
$('restart').onclick = async () => {
  if (posting) return; posting = true;
  if (await command({action: 'restart'})) {
    previousScan = null; previousTime = 0; lastGallery = ''; lastHistory = ''; displayedScan = null; pinnedScan = false;
    toast('Restarting the five-second snapshot mission…');
  }
  setTimeout(() => posting = false, 1500);
};
$('follow-latest').onclick = () => { pinnedScan = false; displayedScan = null; $('follow-latest').hidden = true; };
function showScan(scan) {
  if (!scan || displayedScan === scan.snapshot_id) return;
  displayedScan = scan.snapshot_id;
  $('panorama-empty').hidden = true; $('panorama-wrap').hidden = false;
  $('panorama-image').src = 'data/' + scan.image;
  $('scan-id').textContent = clock(scan.simulation_time_s) + ' / ' + scan.snapshot_id;
  const boxes = $('detection-boxes'); boxes.replaceChildren();
  const chips = $('scan-detections'); chips.replaceChildren();
  for (const item of scan.detections) {
    const box = document.createElement('div'); box.className = 'detection-box';
    const [x, y, w, h] = item.bbox;
    Object.assign(box.style, {left: x*100+'%', top: y*100+'%', width: w*100+'%', height: h*100+'%'});
    const label = document.createElement('span'); label.textContent = item.description + ' · ' + item.sample_id;
    box.append(label); boxes.append(box);
    const chip = document.createElement('div'); chip.className = 'detection-chip'; chip.textContent = item.description;
    const sub = document.createElement('small'); sub.textContent = item.sample_id + ' / ' + item.direction + ' camera';
    chip.append(sub); chips.append(chip);
  }
  if (!scan.detections.length) {
    const p = document.createElement('span'); p.className = 'scene-note';
    p.textContent = 'Snapshot saved · No recognizable lost items visible in this scan.'; chips.append(p);
  }
  document.querySelectorAll('[data-scan]').forEach(b => b.classList.toggle('active', b.dataset.scan === scan.snapshot_id));
}
function history(scans) {
  const key = scans.map(s => s.snapshot_id).join(); if (lastHistory === key) return; lastHistory = key;
  const host = $('scan-history'); host.replaceChildren();
  for (const scan of scans.slice().reverse()) {
    const b = document.createElement('button'); b.dataset.scan = scan.snapshot_id;
    b.textContent = clock(scan.simulation_time_s) + ' · ' + itemCount(scan.detections.length);
    b.classList.toggle('active', b.dataset.scan === displayedScan);
    b.onclick = () => { pinnedScan = true; $('follow-latest').hidden = false; showScan(scan); }; host.append(b);
  }
}
function photo(item) {
  $('empty-photo').hidden = true; $('latest-photo').hidden = false;
  $('latest-photo').src = 'data/' + item.image;
  $('latest-name').textContent = item.description || titles[item.category];
  $('sample-id').textContent = item.sample_id + ' / ' + item.direction.toUpperCase() + ' VIEW';
}
function gallery(items, scans) {
  const key = JSON.stringify(items); if (key === lastGallery) return; lastGallery = key;
  const host = $('gallery'); host.replaceChildren();
  if (!items.length) {
    const e = document.createElement('div'); e.className = 'empty-gallery';
    e.textContent = 'Identified items will appear here after a scheduled 360° capture.'; host.append(e); return;
  }
  for (const item of items) {
    const card = document.createElement('article'); card.className = 'item-card';
    const mat = document.createElement('div'); mat.className = 'item-image';
    const img = document.createElement('img'); img.src = 'data/' + item.image; img.alt = item.description;
    mat.append(img);
    const name = document.createElement('h3'); name.textContent = item.description || titles[item.category];
    const id = document.createElement('small'); id.textContent = item.sample_id;
    const status = document.createElement('span'); status.className = 'listed';
    status.textContent = '✓ Seen at ' + clock(item.simulation_time_s) + ' · ' + item.direction;
    const view = document.createElement('button'); view.textContent = 'View in 360° snapshot ↗';
    view.onclick = () => {
      const scan = scans.find(s => s.snapshot_id === item.snapshot_id);
      if (scan) { pinnedScan = true; $('follow-latest').hidden = false; showScan(scan); $('panorama-wrap').scrollIntoView({behavior: 'smooth', block: 'center'}); }
    };
    card.append(mat, name, id, status, view); host.append(card);
  }
}
async function getJson(path) {
  const r = await fetch('data/' + path + '?t=' + Date.now(), {cache: 'no-store'});
  if (!r.ok) throw Error(path);
  const data = await r.json();
  if (path === 'state.json' && Date.now() - Date.parse(r.headers.get('Last-Modified')) > 6000) data.live = false;
  return data;
}
async function poll() {
  try {
    const [state, items, scans] = await Promise.all([getJson('state.json'), getJson('items.json'), getJson('snapshots.json')]);
    const time = state.simulation_time || 0, live = state.live !== false;
    if (time < previousTime - 1) { previousScan = null; lastGallery = ''; lastHistory = ''; displayedScan = null; pinnedScan = false; }
    previousTime = time;
    $('count').innerHTML = items.length + '<span>/06</span>';
    $('clock').textContent = clock(time);
    $('connection').textContent = live ? 'LIVE SIMULATION' : 'SIMULATION STOPPED';
    $('live-dot').classList.toggle('offline', !live);
    const next = Math.max(0, (state.next_snapshot_s || 5) - time);
    $('activity').textContent = '360° snapshot in ' + next.toFixed(1) + 's · Autonomous patrol';
    $('scan-time').textContent = 'Next capture in ' + next.toFixed(1) + 's (simulation time)';
    $('scan-count').textContent = scans.length + ' snapshots · ' + items.length + ' unique items identified';
    $('view-tag').textContent = state.shot === 'ATRIUM' ? 'ATRIUM VIEW' : state.shot === 'FOLLOW' ? 'FOLLOW ROVER' : '360° ORBIT';
    document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === state.camera));
    history(scans);
    const scan = scans[scans.length - 1] || state.latest_snapshot;
    if (scan) {
      const age = time - scan.simulation_time_s;
      if (previousScan !== scan.snapshot_id) {
        if (live && age >= 0 && age < 1.2) {
          $('flash').classList.remove('fire'); void $('flash').offsetWidth; $('flash').classList.add('fire');
          toast('360° snapshot saved · ' + itemCount(scan.detections.length) + ' identified');
        }
        previousScan = scan.snapshot_id; if (!pinnedScan) showScan(scan);
      }
      if (!pinnedScan && displayedScan !== scan.snapshot_id) showScan(scan);
      if (scan.detections.length) photo(scan.detections[0]);
      else {
        $('latest-photo').hidden = true; $('empty-photo').hidden = false;
        $('latest-name').textContent = 'No items in this snapshot';
        $('sample-id').textContent = 'ALL FOUR DIRECTIONS CAPTURED';
      }
      $('capture-badge').textContent = age < .4 ? 'CAPTURED' : itemCount(scan.detections.length).toUpperCase();
      $('step-capture').className = 'done'; $('step-upload').className = age >= 1.2 ? 'done' : '';
      $('progress-bar').style.width = age < .4 ? '30%' : age < 1.2 ? '70%' : '100%';
      $('upload-label').textContent = age < .4 ? 'Four camera views saved together' : age < 1.2 ? 'Identifying visible items in the snapshot…' : '✓ ' + itemCount(scan.detections.length) + ' identified · Snapshot saved';
    } else {
      $('latest-photo').hidden = true; $('empty-photo').hidden = false;
      $('latest-name').textContent = 'First snapshot at 00:05'; $('sample-id').textContent = 'CAPTURE → ANALYZE → IDENTIFY';
      $('capture-badge').textContent = 'WAITING'; $('upload-label').textContent = 'Snapshot timer is running';
      $('progress-bar').style.width = '0'; $('step-capture').className = ''; $('step-upload').className = '';
      $('panorama-empty').hidden = false; $('panorama-wrap').hidden = true; $('detection-boxes').replaceChildren(); $('scan-detections').replaceChildren();
    }
    gallery(items, scans);
    // Previous replay used object-triggered capture; keep the live view for this new timer workflow.
    $('replay').hidden = true; $('replay').pause(); $('world').hidden = false;
  } catch { $('connection').textContent = 'WAITING FOR WEBOTS'; $('live-dot').classList.add('offline'); }
  finally { setTimeout(poll, 240); }
}
function frame() {
  const img = new Image();
  img.onload = () => { $('world').src = img.src; setTimeout(frame, 180); };
  img.onerror = () => setTimeout(frame, 800);
  img.src = 'data/frame.jpg?t=' + Date.now();
}
poll(); frame();
