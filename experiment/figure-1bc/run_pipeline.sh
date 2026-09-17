#!/usr/bin/env bash
set -euo pipefail

experiment_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$experiment_dir"

mkdir -p results
printf '%s\n' "$$" > results/pipeline-v4.pid
lock_file=results/.figure1bc-v4-pipeline.lock
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another Figure 1(b)(c) pipeline holds $lock_file" >&2
  exit 2
fi

timestamp() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

echo "[$(timestamp)] pipeline_start protocol=figure1bc-v4"

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 2
python3 -m unittest discover -s tests -v
(cd ../threshold && python3 -m unittest -v test_thresholds.py)
python3 -m figure1bc smoke
python3 -m figure1bc dry-run --output results/dry_run_manifest_v4.json

echo "[$(timestamp)] calibration_start"
calibration_run=$(python3 -m figure1bc calibrate | tail -n 1)
echo "[$(timestamp)] calibration_end run=$calibration_run"

calibration_state=$(python3 - "$calibration_run/run_state.json" <<'PY'
import json
import pathlib
import sys

print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["status"])
PY
)
if [[ "$calibration_state" != "selected" ]]; then
  echo "[$(timestamp)] pipeline_stop calibration_status=$calibration_state" >&2
  exit 3
fi

frozen="$calibration_run/frozen_parameters.json"
echo "[$(timestamp)] holdout_start frozen=$frozen"
holdout_run=$(python3 -m figure1bc holdout --frozen "$frozen" | tail -n 1)
echo "[$(timestamp)] holdout_end run=$holdout_run"
echo "[$(timestamp)] pipeline_complete calibration=$calibration_run holdout=$holdout_run summary=$holdout_run/holdout_summary.json"
