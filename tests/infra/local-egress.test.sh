#!/usr/bin/env bash
# Regression test of the opt-in local-egress Compose profile
# (specs/application-foundation/PRDs/002-kubernetes-delivery Requirement 11, Decision 15).
# Without the profile nothing in the local stack reaches outside it; with COMPOSE_PROFILES=local-egress
# in the env file, only the gate joins an outbound network and the backend reaches it alone, as
# host.docker.internal, on the SQL Server, Ollama and LM Studio ports.
# Needs Docker with Compose and python3. It reads neither app/infra/.env nor app/infra/.data, starts
# nothing and prints no configuration value.
# Run: tests/infra/local-egress.test.sh
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
infra="$root/app/infra"
gate_conf="$infra/nginx/nginx.local-egress.conf"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/local-egress-test.XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT
failures=0

check() {
  local description="$1"; shift
  if "$@"; then
    echo "ok   $description"
  else
    echo "FAIL $description"
    failures=$((failures + 1))
  fi
}

# model <env file>: the merged Compose model the stack would run with that env file, as JSON.
# Placeholder secrets satisfy the required variables; the developer's own .env is not read.
model() {
  env -u COMPOSE_PROFILES -u COMPOSE_PROJECT_NAME \
    POSTGRES_PASSWORD=placeholder JWT_PRIVATE_KEY=placeholder REDIS_PASSWORD=placeholder \
    GRAFANA_ADMIN_PASSWORD=placeholder \
    docker compose --project-directory "$infra" --env-file "$1" -p local-egress-test \
    -f "$infra/docker-compose.local.yml" -f "$infra/docker-compose.observability.yml" \
    config --format json
}

: > "$scratch/off.env"
printf 'COMPOSE_PROFILES=local-egress\n' > "$scratch/on.env"
model "$scratch/off.env" > "$scratch/off.json"
model "$scratch/on.env" > "$scratch/on.json"

# assert <model> <name>: one structural rule over the model; exits non-zero when it does not hold.
assert() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

model = json.load(open(sys.argv[1], encoding="utf-8"))
rule = sys.argv[2]
services = model["services"]
networks = model.get("networks", {})


def attached(service):
    return set((services[service].get("networks") or {"default": None}).keys())


def members(network):
    return {name for name in services if network in attached(name)}


outbound = {name for name, spec in networks.items() if not spec.get("internal")}
gate = services.get("local-egress", {})

rules = {
    "no-gate": "local-egress" not in services,
    "no-egress-network": "egress" not in networks,
    "only-edge-is-outbound": outbound == {"edge"},
    "edge-only-proxy-and-dashboard": members("edge") == {"nginx", "grafana"},
    "gate-present": gate.get("profiles") == ["local-egress"],
    "outbound-edge-and-egress": outbound == {"edge", "egress"},
    "egress-only-gate": members("egress") == {"local-egress"},
    "backend-internal-only": attached("backend") <= {"default", "host-gate"}
    and all(networks[name].get("internal") for name in attached("backend")),
    "host-gate-backend-only": members("host-gate") == {"backend"},
    "host-gate-backend-and-gate": members("host-gate") == {"backend", "local-egress"},
    "gate-alias": (gate.get("networks", {}).get("host-gate") or {}).get("aliases")
    == ["host.docker.internal"],
    "gate-networks": set(gate.get("networks", {})) == {"host-gate", "egress"},
    "gate-no-ports": not gate.get("ports") and not gate.get("expose"),
    "gate-hardened": gate.get("read_only") is True
    and gate.get("cap_drop") == ["ALL"]
    and gate.get("user") not in (None, "", "0", "root")
    and "no-new-privileges:true" in (gate.get("security_opt") or []),
    "gate-host-mapping": gate.get("extra_hosts") == ["host.docker.internal=host-gateway"],
    "gate-pinned-image": gate.get("image") == services["nginx"].get("image")
    and "@sha256:" in gate.get("image", ""),
}
sys.exit(0 if rules[rule] else 1)
PY
}

# --- default: the profile is off -------------------------------------------------------------------
check 'default stack has no local-egress gate' assert "$scratch/off.json" no-gate
check 'default stack creates no outbound egress network' assert "$scratch/off.json" no-egress-network
check 'default stack has only the host-facing edge bridge as a non-internal network' \
  assert "$scratch/off.json" only-edge-is-outbound
check 'only the reverse proxy and the dashboard join the edge bridge' \
  assert "$scratch/off.json" edge-only-proxy-and-dashboard
check 'backend joins internal networks only' assert "$scratch/off.json" backend-internal-only
check 'nothing but the backend is on host-gate, so host.docker.internal does not resolve' \
  assert "$scratch/off.json" host-gate-backend-only

# --- opt-in: COMPOSE_PROFILES=local-egress in the env file -----------------------------------------
check 'the env-file setting starts the gate' assert "$scratch/on.json" gate-present
check 'the gate is the only new outbound member' assert "$scratch/on.json" outbound-edge-and-egress
check 'only the gate joins the egress bridge' assert "$scratch/on.json" egress-only-gate
check 'backend still joins internal networks only' assert "$scratch/on.json" backend-internal-only
check 'only the backend and the gate share host-gate' assert "$scratch/on.json" host-gate-backend-and-gate
check 'the gate answers as host.docker.internal on host-gate' assert "$scratch/on.json" gate-alias
check 'the gate joins exactly host-gate and egress' assert "$scratch/on.json" gate-networks
check 'the gate publishes no port' assert "$scratch/on.json" gate-no-ports
check 'the gate runs read-only, unprivileged and without capabilities' \
  assert "$scratch/on.json" gate-hardened
check 'the gate maps host.docker.internal to this computer' assert "$scratch/on.json" gate-host-mapping
check 'the gate uses the pinned reverse proxy image' assert "$scratch/on.json" gate-pinned-image

# --- gate configuration ----------------------------------------------------------------------------
listens="$(sed -n -E 's/^[[:space:]]*listen[[:space:]]+([0-9]+);.*/\1/p' "$gate_conf" | sort -n | tr '\n' ' ')"
check 'the gate listens on 1234, 1433 and 11434 only' test "$listens" = '1234 1433 11434 '
check 'every forward goes to the same port on host.docker.internal' bash -c '
  sed -n -E "s/^[[:space:]]*(listen|proxy_pass)[[:space:]]+([^;]+);.*/\1 \2/p" "$1" |
    awk '"'"'$1 == "listen" { port = $2; next }
      $1 == "proxy_pass" { if ($2 != "host.docker.internal:" port) bad = 1; n++ }
      END { exit (bad || n != 3) }'"'"'
' _ "$gate_conf"
image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["services"]["local-egress"]["image"])' "$scratch/on.json")"
check 'the gate configuration is valid for the pinned image' \
  docker run --rm --network none --add-host host.docker.internal:127.0.0.1 --user 101:101 \
  --read-only --tmpfs /tmp --entrypoint nginx \
  -v "$gate_conf:/etc/nginx/local-egress.conf:ro" "$image" -q -t -c /etc/nginx/local-egress.conf

# --- turning the setting off -----------------------------------------------------------------------
start_task="$(python3 -c 'import json,sys; print(next(t["command"] for t in json.load(open(sys.argv[1]))["tasks"] if t["label"] == "DWH: Uygulamayı başlat"))' "$root/.vscode/tasks.json")"
check 'the start task removes a gate left over after the setting is turned off' \
  grep -qF 'grep -qx local-egress || [ -z "$(scripts/stack.sh ps --all --quiet local-egress 2>/dev/null)" ] || scripts/stack.sh rm --stop --force local-egress; } && scripts/stack.sh up' <<< "$start_task"
check '.env.example documents the setting' grep -qx '# COMPOSE_PROFILES=local-egress' "$infra/.env.example"

if [[ "$failures" -ne 0 ]]; then
  echo "local-egress: $failures check(s) failed" >&2
  exit 1
fi
echo 'local-egress: all checks passed'
