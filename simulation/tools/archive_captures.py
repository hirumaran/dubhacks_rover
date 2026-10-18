#!/usr/bin/env python3
"""Archive this project's generated photos before a fresh run. Does not delete evidence."""
from pathlib import Path
from datetime import datetime
import shutil,json
root=Path(__file__).resolve().parents[1];gallery=root/'gallery';records=json.loads((gallery/'items.json').read_text())
if not records:
 print('Gallery is already empty.');raise SystemExit
archive=root/'logs/capture_archives'/datetime.now().strftime('%Y%m%d-%H%M%S');archive.mkdir(parents=True)
shutil.copy2(gallery/'items.json',archive/'items.json')
for r in records:
 source=gallery/r['image']
 if source.is_file():
  target=archive/r['image'];target.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(source),target)
(gallery/'items.json').write_text('[]\n');print('Previous generated captures archived at',archive)
