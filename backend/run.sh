#!/usr/bin/env bash
# Start the local a-mbl API so phones on the same Wi-Fi can reach it.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Addresses phones can try in the app's connection screen:"
found=0
for ifc in en0 en1 en2 en3 en4; do
  addr="$(ipconfig getifaddr "$ifc" 2>/dev/null || true)"
  if [ -n "$addr" ]; then
    echo "  http://$addr:8000"
    found=1
  fi
done
if [ "$found" -eq 0 ]; then
  echo "  (no Wi-Fi/Ethernet address found — run 'ipconfig getifaddr <interface>' manually)"
fi

conda run --no-capture-output -n a-mbl uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
