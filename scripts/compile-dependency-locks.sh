#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
python3 "$root/scripts/check-dependency-admission.py" --print-inventory
"$root/scripts/stack.sh" exec -T backend sh -lc '
  set -eu
  # requirements-llm.txt is the admitted lock of the application with the optional LangChain set;
  # once requirements.in activates that set, the application lock keeps the admitted versions.
  pip-compile --generate-hashes --output-file=requirements-llm.txt requirements.in requirements-llm.in
  if grep -qx -- "-r requirements-llm.in" requirements.in; then
    pip-compile --generate-hashes --constraint=requirements-llm.txt --output-file=requirements.txt requirements.in
  else
    pip-compile --generate-hashes --output-file=requirements.txt requirements.in
  fi
  pip-compile --allow-unsafe --generate-hashes --constraint=requirements.txt --output-file=requirements-dev.txt requirements-dev.in
'
echo "candidate Python locks regenerated; update dependency-admission.json and run the full gates"
