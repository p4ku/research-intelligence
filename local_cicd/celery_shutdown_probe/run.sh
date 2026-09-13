#!/usr/bin/env bash
# ==============================================================================
# Celery shutdown probe
# Shows what happens to in-flight tasks when the worker is stopped the way Cloud
# Foundry stops it: SIGTERM, then SIGKILL 10 s later (`docker stop` uses the same
# grace). A minimal Celery app with the project's ack settings runs inside the
# backend image, with the sri-worker flags from manifest.yml and the
# `sh -c 'exec …'` process tree the CF launcher produces. Two tasks are started,
# the worker is stopped, and a fresh worker is started to see if they come back.
#
#   bash local_cicd/celery_shutdown_probe/run.sh                  # as deployed (PR #183)
#   REMAP_SIGTERM= bash local_cicd/celery_shutdown_probe/run.sh   # status quo before #183
#
# Prerequisites, from the repo root: `docker compose build worker` and
# `docker compose up -d redis`. Uses Redis db 1 and flushes it.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${IMAGE:-schwarz-research-intelligence-worker}"
NETWORK="${NETWORK:-schwarz-research-intelligence_default}"
REDIS_CONTAINER="${REDIS_CONTAINER:-sri_redis}"
REMAP_SIGTERM="${REMAP_SIGTERM-SIGQUIT}"          # empty = warm shutdown, i.e. the pre-#183 behaviour
SOFT_SHUTDOWN_SECONDS="${SOFT_SHUTDOWN_SECONDS:-3}"

now() { perl -MTime::HiRes=time -e 'printf "%.3f", time'; }
redis() { docker exec "$REDIS_CONTAINER" redis-cli -n 1 "$@"; }

start_worker() {
    docker create --name "$1" --network "$NETWORK" \
        -e DB_HOST= -e PYTHONPATH=/probe \
        -e REMAP_SIGTERM="$REMAP_SIGTERM" -e CELERY_SOFT_SHUTDOWN_SECONDS="$SOFT_SHUTDOWN_SECONDS" \
        "$IMAGE" sh /probe/start.sh >/dev/null
    docker cp "$SCRIPT_DIR" "$1:/probe"
    docker start "$1" >/dev/null
    for _ in $(seq 1 30); do
        if docker logs "$1" 2>&1 | grep -q "ready\."; then return 0; fi
        sleep 1
    done
    echo "worker $1 did not become ready:"; docker logs "$1"; exit 1
}

cleanup() { docker rm -f probe-old probe-new >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup
redis FLUSHDB >/dev/null

echo "== old worker: image=$IMAGE REMAP_SIGTERM='$REMAP_SIGTERM' soft shutdown=${SOFT_SHUTDOWN_SECONDS}s"
start_worker probe-old
echo "process tree (the top process must be celery, not sh):"
docker top probe-old -o pid,ppid,args | head -2 | cut -c1-110
docker exec probe-old celery -A probe call probe.long_task >/dev/null
docker exec probe-old celery -A probe call probe.long_task >/dev/null
sleep 4
echo "tasks running: $(docker logs probe-old 2>&1 | grep -c 'received')"

echo "== docker stop (SIGTERM, SIGKILL after 10 s)"
t0=$(now)
docker stop probe-old >/dev/null
t1=$(now)
printf 'stopped in %.1f s, exit code %s\n' "$(echo "$t1 - $t0" | bc)" "$(docker inspect probe-old --format '{{.State.ExitCode}}')"
docker logs probe-old 2>&1 | grep -E "Soft Shutdown|shutdown \(MainProcess\)|Restoring" || echo "(no shutdown lines: the signal never reached Celery, or it was still waiting when SIGKILL came)"
echo "redis after stop: queued=$(redis LLEN celery) unacked=$(redis HLEN unacked)"

echo "== fresh worker"
start_worker probe-new
sleep 5
docker logs probe-new 2>&1 | grep "received" || echo "(nothing received: the tasks wait for the 1 h visibility timeout)"
redis FLUSHDB >/dev/null
