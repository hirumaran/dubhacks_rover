#!/bin/zsh
cd "$(dirname "$0")"
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"
WEBOTS_BIN="${WEBOTS_HOME:-/Applications/Webots.app}/Contents/MacOS/webots"
if [[ ! -x "$WEBOTS_BIN" ]]; then
  print 'Webots was not found. Open worlds/uw_autonomous.wbt manually in Webots R2025a or newer.'
  read '?Press Return to close.'
  exit 1
fi
exec "$WEBOTS_BIN" --batch --stdout --stderr --mode=realtime --port=1240 "$PWD/worlds/uw_autonomous.wbt"
