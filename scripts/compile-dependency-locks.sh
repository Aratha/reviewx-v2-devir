#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
backend="$root/app/backend"
. "$root/scripts/compose-project.sh"

fail() {
  echo "kilitler yeniden üretilemedi: $*" >&2
  exit 1
}

python3 "$root/scripts/check-dependency-admission.py" --print-inventory

if ! command -v docker >/dev/null 2>&1; then
  fail "Docker bulunamadı; kilitler projenin arka uç imajında üretilir. Docker'ı kurumsal uygulama kataloğundan edinin."
fi
if ! docker info >/dev/null 2>&1; then
  fail "Docker çalışmıyor; Docker'ı başlatıp komutu yeniden çalıştırın."
fi

# Build the backend development image the local stack runs, so the locks carry its Python version
# and platform markers. Compose names it after the project stack.sh uses.
project="$(compose_project_name "$root")" || exit 1
image="$project-backend"
if ! "$root/scripts/stack.sh" build backend; then
  fail "arka uç geliştirme imajı derlenemedi; ayrıntı yukarıdaki Docker çıktısındadır."
fi

# The running backend cannot resolve locks: it has no writable home and the local stack network is
# internal. A disposable container of the same image runs as the invoking user, so the lock files
# stay theirs, gets a temporary home for the pip cache, and reaches the package index over Docker's
# default network; the stack network stays closed. Only the named proxy variables pass through, by
# name, so their values never appear on a command line. No package index setting passes: pip-compile
# writes a non-default index address into the lock files verbatim, credentials included.
if ! docker run --rm --pull never \
  --user "$(id -u):$(id -g)" \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --env HOME=/tmp/dependency-locks-home \
  --env HTTP_PROXY --env HTTPS_PROXY --env NO_PROXY \
  --env http_proxy --env https_proxy --env no_proxy \
  --mount "type=bind,source=$backend,target=/workspace/app/backend" \
  --workdir /workspace/app/backend \
  --entrypoint sh \
  "$image" -c '
  set -eu
  mkdir -p "$HOME"
  # requirements-llm.txt is the admitted lock of the application with the optional LangChain set;
  # once requirements.in activates that set, the application lock keeps the admitted versions.
  pip-compile --generate-hashes --output-file=requirements-llm.txt requirements.in requirements-llm.in
  if grep -qx -- "-r requirements-llm.in" requirements.in; then
    pip-compile --generate-hashes --constraint=requirements-llm.txt --output-file=requirements.txt requirements.in
  else
    pip-compile --generate-hashes --output-file=requirements.txt requirements.in
  fi
  pip-compile --allow-unsafe --generate-hashes --constraint=requirements.txt --output-file=requirements-dev.txt requirements-dev.in
'; then
  fail "pip-compile başarısız oldu; ayrıntı yukarıdaki çıktıdadır."
fi
echo "candidate Python locks regenerated; update dependency-admission.json and run the full gates"
