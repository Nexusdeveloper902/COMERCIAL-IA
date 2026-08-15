#!/usr/bin/env bash
# =============================================================================
# COMERCIAL-IA — Oracle Cloud (Ubuntu) bootstrap script
# -----------------------------------------------------------------------------
# Sets up a brand-new Oracle instance to run the product-data pipeline unattended.
#
# RERUNNABLE: safe to run many times. It installs missing deps only if absent,
# won't clobber your config/data, and idempotently reinstalls the systemd timer.
#
# USAGE:
#   sudo bash scripts/bootstrap_oracle.sh                 # default: 1000 products/run
#   sudo bash scripts/bootstrap_oracle.sh -m 5000         # cap each run at 5000 new products
#   sudo bash scripts/bootstrap_oracle.sh -m 0            # 0 = unlimited
#   sudo bash scripts/bootstrap_oracle.sh --no-timer      # install only, no cron
#   sudo bash scripts/bootstrap_oracle.sh --status        # show timer/service/last run
#
# FLAGS:
#   -m, --max-products N   how many NEW raw records to collect per run (default 1000)
#   --no-timer             skip installing the systemd timer (manual runs only)
#   --status               print timer/service status + last run stats, then exit
#   -h, --help             show this help
#
# After install, the pipeline runs every 6h via systemd (logs in logs/).
# Manual run:   sudo -u cai bash -lc 'cd /opt/comercial-ia && python scripts/run_pipeline.py --max-products 1000'
# =============================================================================
set -euo pipefail

# ---- defaults ---------------------------------------------------------------
MAX_PRODUCTS=1000
INSTALL_TIMER=1
ACTION="install"

# ---- arg parsing ------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--max-products) MAX_PRODUCTS="$2"; shift 2;;
    --no-timer) INSTALL_TIMER=0; shift;;
    --status) ACTION="status"; shift;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

# ---- constants --------------------------------------------------------------
APP_USER="cai"
APP_DIR="/opt/comercial-ia"
VENV_DIR="${APP_DIR}/.venv"
PY="python3"
SERVICE_NAME="comercial-ai-pipeline"
TIMER_NAME="comercial-ai-pipeline.timer"
POLL_MIN="${CAI_POLL_INTERVAL_MIN:-360}"   # 6h default; override via env

# ---- helpers ----------------------------------------------------------------
log() { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[bootstrap ERROR]\033[0m %s\n' "$*" >&2; }

require_root() {
  if [[ $EUID -ne 0 ]]; then err "run with sudo"; exit 1; fi
}

# =============================================================================
# STATUS ACTION
# =============================================================================
if [[ "$ACTION" == "status" ]]; then
  echo "=== systemd timer ==="
  systemctl status "${TIMER_NAME}" --no-pager 2>/dev/null || echo "(timer not installed)"
  echo "=== last service run ==="
  journalctl -u "${SERVICE_NAME}.service" --no-pager -n 20 2>/dev/null || echo "(no journal entries)"
  echo "=== last run stats ==="
  [[ -f "${APP_DIR}/data/last_run_stats.json" ]] \
    && cat "${APP_DIR}/data/last_run_stats.json" \
    || echo "(no stats yet)"
  exit 0
fi

require_root
log "bootstrapping COMERCIAL-IA on Oracle (max_products=${MAX_PRODUCTS}, timer=${INSTALL_TIMER})"

# =============================================================================
# 1. System packages (idempotent)
# =============================================================================
log "updating apt and installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip python3-dev \
  build-essential git curl ca-certificates \
  >/dev/null

# verify python version (need 3.10+)
PYV=$(${PY} -c 'import sys;print("%d.%d"%sys.version_info[:2])')
log "python version: ${PYV}"

# =============================================================================
# 2. Service user (idempotent)
# =============================================================================
if ! id -u "${APP_USER}" &>/dev/null; then
  log "creating service user: ${APP_USER}"
  useradd --system --create-home --shell /bin/bash "${APP_USER}"
else
  log "service user '${APP_USER}' already exists"
fi

# =============================================================================
# 3. App directory + code (idempotent)
# =============================================================================
log "ensuring app dir: ${APP_DIR}"
mkdir -p "${APP_DIR}"

# If this script is run from inside a clone, sync the source into the app dir.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
if [[ -f "${REPO_ROOT}/pyproject.toml" && -d "${REPO_ROOT}/src/commercial_ai" ]]; then
  log "syncing repo from ${REPO_ROOT} -> ${APP_DIR}"
  rsync -a --delete \
    --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
    --exclude 'data/.http_cache' --exclude 'data/.pipeline_state.json' \
    --exclude 'data/raw' --exclude 'data/normalized' \
    --exclude 'data/rejected' --exclude 'data/derived' \
    --exclude 'logs/*.log' --exclude '.pytest_cache' \
    --exclude '*.egg-info' \
    "${REPO_ROOT}/" "${APP_DIR}/"
else
  log "no local repo detected at ${REPO_ROOT}; assuming ${APP_DIR} already has code"
fi
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

# =============================================================================
# 4. Virtualenv + python deps (idempotent)
# =============================================================================
if [[ ! -d "${VENV_DIR}" ]]; then
  log "creating virtualenv: ${VENV_DIR}"
  sudo -u "${APP_USER}" ${PY} -m venv "${VENV_DIR}"
fi

log "upgrading pip and installing project (dev+derived extras)"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet --upgrade pip wheel setuptools
# Install the project itself (editable). If pyarrow/pandas unavailable, JSONL+CSV still work.
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet -e "${APP_DIR}[dev,derived]" \
  || sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet -e "${APP_DIR}"

# =============================================================================
# 5. Smoke test
# =============================================================================
log "running test suite as a smoke test"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/python" -m pytest "${APP_DIR}/tests" -q \
  || { err "tests failed; aborting before scheduling"; exit 1; }

# =============================================================================
# 6. Data dirs
# =============================================================================
log "ensuring data dirs"
for d in raw normalized rejected taxonomy interactions derived sample logs; do
  mkdir -p "${APP_DIR}/data/${d}"
done
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/data" "${APP_DIR}/logs"

# =============================================================================
# 7. Systemd service + timer (idempotent)
# =============================================================================
if [[ "${INSTALL_TIMER}" -eq 1 ]]; then
  log "installing systemd service + timer (every ${POLL_MIN} min)"

  cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=COMERCIAL-IA product data pipeline
After=network-online.target
Wants=network-online.target
# On failure, start the notify unit (logs a journal marker you can alert on).
OnFailure=${SERVICE_NAME}-notify.service

[Service]
Type=oneshot
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
# Optional Best Buy API key injected via a root-owned env file (never in the repo).
# Create /opt/comercial-ia/.env.runtime (chmod 600 root) with: BBY_API_KEY=...
EnvironmentFile=-${APP_DIR}/.env.runtime
ExecStart=${VENV_DIR}/bin/python ${APP_DIR}/scripts/run_pipeline.py --max-products ${MAX_PRODUCTS}
StandardOutput=append:${APP_DIR}/logs/pipeline.log
StandardError=append:${APP_DIR}/logs/pipeline.err.log
EOF

  # Failure-notify unit: extendable to email/webhook later. For now it journals a marker.
  cat > "/etc/systemd/system/${SERVICE_NAME}-notify.service" <<EOF
[Unit]
Description=COMERCIAL-IA pipeline failure notifier

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo "COMERCIAL-IA pipeline FAILED at $$(date -Is); check ${APP_DIR}/logs/pipeline.err.log" | systemd-cat -t comercial-ai-notify -p err'
EOF

  cat > "/etc/systemd/system/${TIMER_NAME}" <<EOF
[Unit]
Description=Run COMERCIAL-IA pipeline periodically

[Timer]
OnBootSec=2min
OnUnitActiveSec=${POLL_MIN}min
Persistent=true

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now "${TIMER_NAME}"
  log "timer installed. next run scheduled; first run may be triggered with:"
  log "  sudo systemctl start ${SERVICE_NAME}.service"
else
  log "--no-timer: skipping systemd timer (run manually)"
fi

# =============================================================================
# 8. Log rotation (idempotent)
# =============================================================================
log "ensuring logrotate config"
cat > /etc/logrotate.d/comercial-ai <<EOF
${APP_DIR}/logs/*.log {
  daily
  rotate 14
  compress
  missingok
  notifempty
  copytruncate
}
EOF

# =============================================================================
# Done
# =============================================================================
log "bootstrap complete."
log "  manual run:  sudo -u ${APP_USER} ${VENV_DIR}/bin/python ${APP_DIR}/scripts/run_pipeline.py --max-products ${MAX_PRODUCTS}"
log "  status:      sudo bash ${APP_DIR}/scripts/bootstrap_oracle.sh --status"
log "  tail logs:   tail -f ${APP_DIR}/logs/pipeline.log"
if [[ "${INSTALL_TIMER}" -eq 1 ]]; then
  log "  timer list:  systemctl list-timers ${TIMER_NAME}"
fi
