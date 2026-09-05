#!/bin/bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO"

git ls-files '*.sh' bin/* | xargs -n1 bash -n
python3 -m unittest discover -s tests -v
bash tests/test_apply.sh
bash tests/test_apply_ts.sh
bash tests/test_second_opinion.sh
bash tests/test_pressure.sh
