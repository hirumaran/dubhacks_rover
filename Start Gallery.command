#!/bin/zsh
cd "$(dirname "$0")"
exec python3 tools/serve_gallery.py
