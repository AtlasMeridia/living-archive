#!/bin/zsh
# Nightly Living Archive photo batch — invoked by com.atlasm.living-archive (launchd).
# Processes any new/unprocessed photos under MEDIA_ROOT with a 2-hour budget,
# pushing results to Immich. Exits in ~2 min when there is nothing to do.
# caffeinate keeps the Mac awake for the duration of the run only.

cd "$(dirname "$0")/.." || exit 1
exec /usr/bin/caffeinate -i .venv/bin/python -m src.pipeline photo --hours 2 --push
