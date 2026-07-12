#!/bin/zsh
# Nightly Living Archive photo batch — invoked by com.atlasm.living-archive (launchd).
# Processes any new/unprocessed photos under MEDIA_ROOT with a 2-hour budget,
# pushing results to Immich. Exits in ~2 min when there is nothing to do.
# caffeinate keeps the Mac awake for the duration of the run only.

umask 077
cd "$(dirname "$0")/.." || exit 1
mkdir -p private || exit 1
chmod 700 private || exit 1
for log_file in private/*.log*(N); do
  chmod 600 "$log_file" || exit 1
done
exec /usr/bin/caffeinate -i .venv/bin/python -m src.pipeline photo --hours 2 --push
