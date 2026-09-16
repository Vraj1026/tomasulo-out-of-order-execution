#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3.10+ is required.' >&2
  exit 2
fi
python3 -c 'import sys; sys.exit("Python 3.10+ is required.") if sys.version_info < (3, 10) else None'
python3 -m unittest discover -s tests -v
python3 -m tomasulo examples/hazards.asm --check --out build/hazards
echo 'Open build/hazards/trace.html in your browser.'
