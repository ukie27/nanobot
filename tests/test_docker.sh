#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

image_name="career-console-test"
container_name="career-console-test-run"
workspace_dir="$(mktemp -d)"
workspace_mount="$workspace_dir"

# Git Bash rewrites Linux-looking container arguments on Windows. Preserve
# container paths and pass an explicit Windows host path for the bind mount.
if command -v cygpath >/dev/null 2>&1; then
    workspace_mount="$(cygpath -w "$workspace_dir")"
    export MSYS_NO_PATHCONV=1
fi

cleanup() {
    docker rm -f "$container_name" >/dev/null 2>&1 || true
    docker image rm -f "$image_name" >/dev/null 2>&1 || true
    rm -rf "$workspace_dir"
}
trap cleanup EXIT

docker build -t "$image_name" .

docker run --rm \
    -v "$workspace_mount:/data/CareerConsole" \
    "$image_name" setup --workspace /data/CareerConsole

status_output="$(docker run --rm \
    -v "$workspace_mount:/data/CareerConsole" \
    "$image_name" status --workspace /data/CareerConsole)"

printf '%s\n' "$status_output"
printf '%s\n' "$status_output" | grep -F "CareerConsole v"
printf '%s\n' "$status_output" | grep -F "Workspace: /data/CareerConsole"
printf '%s\n' "$status_output" | grep -F "Revision: 20260726_0026"

docker run --rm \
    -v "$workspace_mount:/data/CareerConsole" \
    "$image_name" doctor --workspace /data/CareerConsole

docker run --rm --name "$container_name" \
    -v "$workspace_mount:/data/CareerConsole" \
    -p 127.0.0.1:18765:8765 \
    "$image_name" serve --workspace /data/CareerConsole \
    --host 0.0.0.0 --port 8765 &

for _ in $(seq 1 30); do
    if curl --fail --silent http://127.0.0.1:18765/health/ready >/dev/null; then
        exit 0
    fi
    sleep 1
done

docker logs "$container_name"
exit 1
