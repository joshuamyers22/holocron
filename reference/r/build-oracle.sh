#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /absolute/path/to/rms-master" >&2
  exit 2
fi

rms_source=$1
if [[ ! -d "$rms_source" || ! -f "$rms_source/DESCRIPTION" ]]; then
  echo "invalid rms source directory: $rms_source" >&2
  exit 2
fi

project_root=$(cd "$(dirname "$0")/../.." && pwd)

docker build \
  --build-context "rms_source=$rms_source" \
  --file "$project_root/reference/r/Dockerfile" \
  --label "org.opencontainers.image.title=Holocron rms oracle" \
  --label "org.opencontainers.image.version=8.2-0" \
  --tag "holocron-rms-oracle:8.2-0" \
  "$project_root"
