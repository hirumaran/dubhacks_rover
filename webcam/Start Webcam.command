#!/bin/zsh
cd -- "${0:A:h}/.."
if [[ ! -x simulation/perception_bridge/.venv/bin/python ]]; then
  echo "Install the bridge environment first (see webcam/README.md)."
  exit 1
fi
simulation/perception_bridge/.venv/bin/python webcam/launch.py
