#!/usr/bin/env bash
# Provision a plugin_host device in the Device Connect portal.
#
# Usage:
#   export DEVICE_CONNECT_PORTAL_URL=http://portal.deviceconnect.dev
#   ./examples/portal-provision.sh [device-id] [tenant]
#
# Requires dc-portalctl (device-connect-server) on PATH — see AGENTS.md.

set -euo pipefail

DEVICE_ID="${1:-plugin-host-001}"
TENANT="${2:-${TENANT:-default}}"
PORTAL_URL="${DEVICE_CONNECT_PORTAL_URL:-http://portal.deviceconnect.dev}"
CREDS_DIR="${PORTAL_CREDENTIALS_DIR:-${HOME}/.config/device-connect}"
CREDS_FILE="${CREDS_DIR}/${DEVICE_ID}.creds.json"

mkdir -p "${CREDS_DIR}"

if ! command -v dc-portalctl >/dev/null 2>&1; then
  echo "dc-portalctl not found. Install with:" >&2
  echo "  python3 -m venv ~/.dc-portalctl/venv && ~/.dc-portalctl/venv/bin/pip install device-connect-server" >&2
  exit 1
fi

export DEVICE_CONNECT_PORTAL_URL="${PORTAL_URL}"

echo "Provisioning plugin_host device:"
echo "  device_id=${DEVICE_ID}"
echo "  tenant=${TENANT}"
echo "  portal=${PORTAL_URL}"
echo "  credentials=${CREDS_FILE}"

dc-portalctl devices provision "${DEVICE_ID}" \
  --type plugin_host \
  --tenant "${TENANT}" \
  --output "${CREDS_FILE}"

echo ""
echo "Start the driver:"
echo "  device-connect-plugin-driver \\"
echo "    --portal \\"
echo "    --portal-credentials ${CREDS_FILE} \\"
echo "    --nats-credentials-file ${CREDS_FILE} \\"
echo "    --device-id ${DEVICE_ID} \\"
echo "    --tenant ${TENANT}"
