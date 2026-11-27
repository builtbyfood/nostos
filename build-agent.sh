#!/usr/bin/env bash
# Nostos 0.2.4 - build-agent.sh
# Builds the Windows app (NostosAgent.exe) from the Go source in agent/.
# Go 1.21 or newer is the only requirement; it cross-compiles from Linux.
#
#   ./build-agent.sh          build nostos/windows_helper/NostosAgent.exe
#   ./build-agent.sh --linux  also build ./nostos-agent for this machine (testing)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/agent"
go vet ./...
GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w" \
    -o "$HERE/nostos/windows_helper/NostosAgent.exe" .
echo "Built nostos/windows_helper/NostosAgent.exe"
if [[ "${1:-}" == "--linux" ]]; then
    go build -trimpath -o "$HERE/nostos-agent" .
    echo "Built ./nostos-agent"
fi
