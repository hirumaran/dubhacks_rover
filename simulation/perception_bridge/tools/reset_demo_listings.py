"""List or delete the found_items listings this rover created as demo data (and their photos).

Use it to reset between demo runs or to remove bad listings. Only rows with this rover's
ROVER_ID and is_demo = true are touched. Without --yes it only prints what it would delete.

    python tools/reset_demo_listings.py                      # list the rover's demo listings
    python tools/reset_demo_listings.py --title "green" --yes  # delete listings whose title contains "green"
    python tools/reset_demo_listings.py --all --yes            # delete all of them

Needs the project's service-role key: SUPABASE_SERVICE_ROLE_KEY, or a logged-in Supabase CLI.
Deleting a listing also deletes its matches and notifications (database cascade).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

PROJECT_REF = os.environ.get("SUPABASE_PROJECT_REF", "salsusdncqbtrkcqxdkg")
BASE = f"https://{PROJECT_REF}.supabase.co"


def service_key() -> str:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if key:
        return key
    with tempfile.TemporaryDirectory() as d:  # the CLI drops a supabase/.temp folder in its cwd
        out = subprocess.run(["supabase", "projects", "api-keys", "--project-ref", PROJECT_REF, "-o", "json"],
                             cwd=d, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("Set SUPABASE_SERVICE_ROLE_KEY or log in with `supabase login`.")
    return next(k["api_key"] for k in json.loads(out.stdout) if k.get("name") == "service_role")


def call(method: str, url: str, key: str, body: dict | None = None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json", "Prefer": "return=representation"})
    with urllib.request.urlopen(req, timeout=60) as res:
        raw = res.read()
        return json.loads(raw) if raw else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--title", action="append", default=[], help="only listings whose title contains this (any of)")
    ap.add_argument("--all", action="store_true", help="every demo listing from this rover")
    ap.add_argument("--yes", action="store_true", help="actually delete")
    args = ap.parse_args()
    if not config.ROVER_ID:
        sys.exit("ROVER_ID is not set in simulation/perception_bridge/.env")

    key = service_key()
    query = urllib.parse.urlencode({
        "select": "id,title,image_path,image_paths,created_at",
        "rover_id": f"eq.{config.ROVER_ID}", "is_demo": "eq.true", "order": "created_at",
    })
    rows = call("GET", f"{BASE}/rest/v1/found_items?{query}", key) or []
    if args.title:
        rows = [r for r in rows if any(t.lower() in r["title"].lower() for t in args.title)]
    elif not args.all:
        for r in rows:
            print(f"  {r['created_at'][:19]}  {r['title']}  ({r['id']})")
        print(f"{len(rows)} demo listing(s) from this rover. Pass --title or --all, plus --yes, to delete.")
        return

    for r in rows:
        print(f"  {'deleting' if args.yes else 'would delete'}: {r['title']}  ({r['id']})")
    if not args.yes or not rows:
        print(f"{len(rows)} listing(s){'' if args.yes else ' would be deleted (add --yes)'}.")
        return

    ids = ",".join(r["id"] for r in rows)
    call("DELETE", f"{BASE}/rest/v1/found_items?id=in.({ids})", key)
    photos = sorted({p for r in rows for p in [r["image_path"], *(r["image_paths"] or [])]
                     if p and not p.startswith("http")})
    if photos:
        call("DELETE", f"{BASE}/storage/v1/object/found-photos", key, {"prefixes": photos})
    print(f"Deleted {len(rows)} listing(s) and {len(photos)} photo(s).")


if __name__ == "__main__":
    main()
