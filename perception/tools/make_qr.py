#!/usr/bin/env python3
"""Generate printable desk QR codes for Campus Scout.

Each station in kiosk/stations.json becomes a PNG card whose QR opens:

    {PUBLIC_APP_URL}/?station={station_id}

Campus security / librarians print `perception/kiosk/qr/*.png` (or the
combined print.html sheet) and tape them on desks.

Examples:
  python tools/make_qr.py
  python tools/make_qr.py --url https://scout.example.edu
  python tools/make_qr.py --lan            # this machine's Wi-Fi IP + KIOSK_PORT
  python tools/make_qr.py --station gates-atrium --size 12
"""
from __future__ import annotations
import argparse
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from dispatch import load_stations, station_url


def detect_lan_ip() -> str | None:
    """Best-effort LAN IP of this machine (works offline via the route table)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # TEST-NET, no packets actually sent
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        s.close()


def _qr_module():
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_H
        from PIL import Image, ImageDraw, ImageFont
        return qrcode, ERROR_CORRECT_H, Image, ImageDraw, ImageFont
    except ImportError as e:
        raise SystemExit(
            "make_qr.py needs pillow + qrcode. From perception/: "
            ".venv/bin/pip install -r requirements.txt"
        ) from e


def _font(size: int):
    from PIL import ImageFont
    for name in ("Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_card(station: dict, url: str, box: int):
    qrcode, ERROR_CORRECT_H, Image, ImageDraw, ImageFont = _qr_module()
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=box, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#102016", back_color="white").convert("RGB")

    pad = 48
    title_h = 70
    footer_h = 90
    w = qr_img.width + pad * 2
    h = qr_img.height + pad * 2 + title_h + footer_h
    card = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, w, 18), fill="#c8f56a")
    title = _font(28)
    small = _font(16)
    tiny = _font(13)
    draw.text((pad, 28), "CAMPUS SCOUT", fill="#3d6b1f", font=small)
    draw.text((pad, 50), "Lost something? Scan to report", fill="#102016", font=title)
    card.paste(qr_img, (pad, pad + title_h))
    y = pad + title_h + qr_img.height + 16
    draw.text((pad, y), station["name"], fill="#102016", font=small)
    draw.text(
        (pad, y + 28),
        "Nearest rover searches this building and nearby spots.",
        fill="#44554a",
        font=tiny,
    )
    draw.text((pad, y + 50), f"station: {station['id']}", fill="#7a8a80", font=tiny)
    return card


def write_print_sheet(out_dir: Path, stations: list[dict], base: str) -> Path:
    cards = []
    for s in stations:
        rel = f"{s['id']}.png"
        cards.append(
            f'<figure><img src="{rel}" alt="{s["name"]}" />'
            f"<figcaption>{s['name']}<br/><code>{station_url(base, s['id'])}</code></figcaption></figure>"
        )
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Campus Scout QR print sheet</title>
<style>
  body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; color: #102016; }}
  h1 {{ font-size: 20px; }}
  p {{ color: #44554a; max-width: 40rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 24px; }}
  figure {{ margin: 0; page-break-inside: avoid; border: 1px solid #ddd; padding: 8px; }}
  img {{ width: 100%; height: auto; }}
  figcaption {{ font-size: 12px; margin-top: 8px; }}
  @media print {{ button {{ display: none; }} }}
</style></head><body>
<h1>Campus Scout — print and tape these on desks</h1>
<p>Generated for <code>{base}</code>. If the public URL changes, re-run
<code>python tools/make_qr.py --url …</code> and reprint.</p>
<button onclick="window.print()">Print</button>
<div class="grid">{''.join(cards)}</div>
</body></html>
"""
    path = out_dir / "print.html"
    path.write_text(html)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=config.PUBLIC_APP_URL, help="Public kiosk origin the QR must open")
    ap.add_argument("--lan", action="store_true",
                    help="Use this machine's LAN IP + KIOSK_PORT (phone demo on the same Wi-Fi)")
    ap.add_argument("--station", help="Only this station id")
    ap.add_argument("--out", default=str(config.KIOSK_DIR / "qr"), help="Output directory")
    ap.add_argument("--size", type=int, default=10, help="QR box size (print scale)")
    args = ap.parse_args()

    base = args.url
    if args.lan:
        ip = detect_lan_ip()
        if ip:
            base = f"http://{ip}:{config.KIOSK_PORT}"
            print(f"[qr] --lan -> {base}")
        else:
            print("[qr] could not detect a LAN IP; keeping", base, file=sys.stderr)

    stations = list(load_stations().values())
    if args.station:
        stations = [s for s in stations if s["id"] == args.station]
        if not stations:
            raise SystemExit(f"unknown station {args.station}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for s in stations:
        url = station_url(base, s["id"])
        card = render_card(s, url, args.size)
        dest = out / f"{s['id']}.png"
        card.save(dest, "PNG")
        manifest.append({"id": s["id"], "name": s["name"], "url": url, "file": dest.name})
        print(f"wrote {dest}  ->  {url}")

    (out / "manifest.json").write_text(json.dumps({"base_url": base, "cards": manifest}, indent=2))
    sheet = write_print_sheet(out, stations, base)
    print(f"print sheet: {sheet}")
    if "localhost" in base or "127.0.0.1" in base:
        print("NOTE: localhost QRs only work on the phone sharing this machine's network. "
              "Regenerate with --lan or --url https://your-deploy before taping them up.")


if __name__ == "__main__":
    main()
