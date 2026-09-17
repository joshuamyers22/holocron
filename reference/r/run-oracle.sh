#!/usr/bin/env bash
set -euo pipefail

docker run \
  --rm \
  --interactive \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --memory 2g \
  --cpus 2 \
  holocron-rms-oracle:8.2-0
