#!/bin/zsh
cd -- "${0:A:h}"
LOCAL_VISION=1 DRY_RUN=true python3 tools/launch_showcase.py --fresh
