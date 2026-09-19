#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/deploy-uno-q-wifi.sh
# Purpose: Deploy the application over authenticated SSH, preserve device data, restart it, and verify health.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-16 - Skip privileged maintenance safely when sudo needs an unseen password and print the follow-up commands.
#   2026-09-11 - Adopted the virtualglove App Lab directory with one-time local data migration.
#   2026-09-11 - Migrated App Lab containers to the virtualglove Compose project.
#   2026-09-11 - Verify the Engineering Toolkit guide and PDF during deployment.
#   2026-09-10 - Rotate routine payload backups while preserving named engineering evidence.
#   2026-09-06 - Avoid reinstalling an identical enabled Wi-Fi sampler during updates.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Verified the Rock Paper Scissors page during deployment.
#   2026-09-05 - Verified the corrected closed-hand Academy artwork.
#   2026-09-04 - Verified current guide titles, individual gestures, and Pixel Pal.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Verified Help guides and artwork; added an IP fallback for mDNS pauses.
#   2026-09-03 - Used staged SFTP uploads and terminal-backed UNO Q commands.
#   2026-09-03 - Verified every Help guide and all gameplay table illustrations.
#   2026-09-03 - Deployed and verified every allowlisted public PDF guide.
#   2026-09-03 - Preserved VirtualGlove as the UNO Q default startup app.
#   2026-09-03 - Restored shutdown readiness when the host helper is active.
#   2026-09-03 - Allowed three minutes for a cold App Lab runtime startup.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

UNO_TARGET="${UNO_Q_SSH_TARGET:-arduino@arduiain.local}"
REMOTE_APP_DIR="${UNO_Q_APP_DIR:-/home/arduino/ArduinoApps/virtualglove}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'USAGE'
Usage: scripts/deploy-uno-q-wifi.sh [user@uno-q-host]

Deploy the VirtualGlove Linux application over an authenticated SSH
connection, preserve device settings, expose ports 8088 and 8443, keep it as
the default startup app, restart the container, and verify its status. The
default target is:

  arduino@arduiain.local

Environment overrides:
  UNO_Q_SSH_TARGET  SSH destination
  UNO_Q_SSH_IDENTITY  Optional private-key path for this UNO Q
  UNO_Q_APP_DIR     Remote App Lab application directory
  VIRTUALGLOVE_DEPLOY_BACKUPS_KEEP  Routine payload backups to retain (default: 12)
USAGE
  exit 0
fi

if [[ $# -gt 1 ]]; then
  echo "error: expected at most one SSH destination" >&2
  exit 2
fi

if [[ $# -eq 1 ]]; then
  UNO_TARGET="$1"
fi

readonly UNO_TARGET REMOTE_APP_DIR
DEPLOY_BACKUPS_KEEP="${VIRTUALGLOVE_DEPLOY_BACKUPS_KEEP:-12}"
if [[ ! "${DEPLOY_BACKUPS_KEEP}" =~ ^[0-9]+$ ]] \
    || (( DEPLOY_BACKUPS_KEEP < 2 || DEPLOY_BACKUPS_KEEP > 100 )); then
  echo "error: VIRTUALGLOVE_DEPLOY_BACKUPS_KEEP must be an integer from 2 to 100" >&2
  exit 2
fi
readonly DEPLOY_BACKUPS_KEEP
readonly UNO_HOST="${UNO_TARGET#*@}"
readonly REMOTE_COMPOSE="${REMOTE_APP_DIR}/.cache/app-compose.yaml"
readonly REMOTE_ARCHIVE="/tmp/virtualglove-deploy.tar.gz"
readonly LOCAL_ARCHIVE="$(mktemp)"
readonly LOCAL_METADATA_DIR="$(mktemp -d)"
SSH_OPTIONS=(
  -o BatchMode=yes
  -o ConnectTimeout=30
  -o ServerAliveInterval=10
  -o ServerAliveCountMax=12
)
if [[ -n "${UNO_Q_SSH_IDENTITY:-}" ]]; then
  if [[ ! -f "${UNO_Q_SSH_IDENTITY}" ]]; then
    echo "error: UNO_Q_SSH_IDENTITY is not a readable file" >&2
    exit 2
  fi
  SSH_OPTIONS+=(-i "${UNO_Q_SSH_IDENTITY}")
fi
readonly -a SSH_OPTIONS

# Always remove the local staging archive, including after an interrupted upload.
cleanup() {
  rm -f "${LOCAL_ARCHIVE}"
  rm -rf "${LOCAL_METADATA_DIR}"
}
trap cleanup EXIT

echo "Checking ${UNO_TARGET}..."
ssh -tt "${SSH_OPTIONS[@]}" "${UNO_TARGET}" true >/dev/null
UNO_CONNECTION="$(ssh "${SSH_OPTIONS[@]}" "${UNO_TARGET}" 'printf "%s" "$SSH_CONNECTION"' 2>/dev/null | tr -d '\r' || true)"
read -r _UNO_CLIENT _UNO_CLIENT_PORT UNO_HEALTH_HOST _UNO_SERVER_PORT <<< "${UNO_CONNECTION}"
if [[ -z "${UNO_HEALTH_HOST}" ]]; then
  UNO_HEALTH_HOST="${UNO_HOST}"
fi
UNO_HEALTH_AUTHORITY="${UNO_HEALTH_HOST}"
if [[ "${UNO_HEALTH_AUTHORITY}" == *:* && "${UNO_HEALTH_AUTHORITY}" != \[*\] ]]; then
  UNO_HEALTH_AUTHORITY="[${UNO_HEALTH_AUTHORITY}]"
fi
readonly UNO_CONNECTION UNO_HEALTH_HOST UNO_HEALTH_AUTHORITY

# Never open a hidden sudo password prompt during a remote deployment. Host
# helpers and firmware are maintained only when sudo is already non-interactive;
# otherwise the application still deploys and the exact follow-up is printed.
PRIVILEGED_READY=false
if ssh "${SSH_OPTIONS[@]}" "${UNO_TARGET}" 'sudo -n true' >/dev/null 2>&1; then
  PRIVILEGED_READY=true
else
  echo "Privileged host maintenance needs the UNO Q sudo password; deploying the application without prompting."
fi
readonly PRIVILEGED_READY

echo "Uploading VirtualGlove over Wi-Fi..."
python3 "${SCRIPT_DIR}/application-payload.py" "${LOCAL_METADATA_DIR}" \
  --include-engineering --precompiled-matrix
COPYFILE_DISABLE=1 tar -C "${LOCAL_METADATA_DIR}" -czf "${LOCAL_ARCHIVE}" .
scp "${SSH_OPTIONS[@]}" "${LOCAL_ARCHIVE}" "${UNO_TARGET}:${REMOTE_ARCHIVE}"
ssh -tt "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
  "set -eu; stage=\$(mktemp -d /tmp/virtualglove-payload.XXXXXX); trap 'rm -rf \"\$stage\"' EXIT; tar --warning=no-unknown-keyword -C \"\$stage\" -xzf '${REMOTE_ARCHIVE}'; python3 \"\$stage/scripts/installation-manifest.py\" '${REMOTE_APP_DIR}' --source \"\$stage\" --backup \"\$HOME/virtualglove-backups/payload-\$(date +%Y%m%d-%H%M%S)-\$\$\"; python3 \"\$stage/scripts/rotate-deployment-backups.py\" \"\$HOME/virtualglove-backups\" --keep '${DEPLOY_BACKUPS_KEEP}' || echo 'warning: routine deployment-backup rotation did not complete' >&2; rm -f '${REMOTE_ARCHIVE}'"

echo "Preparing the VirtualGlove App Lab runtime..."
ssh -tt "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
  "if test ! -f '${REMOTE_COMPOSE}'; then arduino-app-cli app start '${REMOTE_APP_DIR}'; fi"

echo "Ensuring the secure setup port is published..."
ssh -tt "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
  "REMOTE_COMPOSE='${REMOTE_COMPOSE}' python3 -c \"import os, pathlib; p=pathlib.Path(os.environ['REMOTE_COMPOSE']); lines=p.read_text().splitlines(); found=any(line.strip() == '- 8443:8443' for line in lines); index=next((i for i, line in enumerate(lines) if line.strip() == '- 8088:8088'), None); assert found or index is not None, 'port 8088 is missing from App Lab compose file'; lines if found else lines.insert(index + 1, lines[index].replace('8088:8088', '8443:8443')); p.write_text('\\n'.join(lines) + '\\n')\""

echo "Configuring persistent local hostname resolution..."
ssh "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
  "python3 '${REMOTE_APP_DIR}/scripts/configure-uno-q-mdns.py' '${REMOTE_COMPOSE}' --project-only && { test ! -S /run/avahi-daemon/socket || python3 '${REMOTE_APP_DIR}/scripts/configure-uno-q-mdns.py' '${REMOTE_COMPOSE}'; }"

if [[ "${PRIVILEGED_READY}" == true ]]; then
  echo "Updating VirtualGlove host-service names..."
  ssh "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
    "sudo -n python3 '${REMOTE_APP_DIR}/scripts/setup-machine.py' uno-q --runtime-names-only"

  echo "Flashing the compiled VirtualGlove Matrix firmware..."
  ssh "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
    "sudo -n python3 '${REMOTE_APP_DIR}/scripts/flash-matrix-firmware.py' '${REMOTE_APP_DIR}/firmware/matrix'"
else
  echo "Skipping host-service reinstall and Matrix flash; both require an interactive sudo password."
fi

echo "Checking the host helpers..."
ssh -tt "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
  "mkdir -p '${REMOTE_APP_DIR}/data'; if systemctl is-active --quiet virtualglove-system-shutdown.path; then touch '${REMOTE_APP_DIR}/data/.shutdown-enabled'; else rm -f '${REMOTE_APP_DIR}/data/.shutdown-enabled'; echo 'warning: install scripts/install-uno-q-shutdown-helper.sh to enable Dashboard shutdown' >&2; fi; if systemctl is-active --quiet virtualglove-camera-recovery.path; then touch '${REMOTE_APP_DIR}/data/.camera-recovery-enabled'; else rm -f '${REMOTE_APP_DIR}/data/.camera-recovery-enabled'; echo 'warning: install scripts/install-uno-q-shutdown-helper.sh to enable guarded USB camera recovery' >&2; fi"

echo "Restarting the UNO Q application..."
ssh -tt "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
  "arduino-app-cli properties set default '${REMOTE_APP_DIR}' && APP_HOME='${REMOTE_APP_DIR}' docker compose -f '${REMOTE_COMPOSE}' up -d --force-recreate"

echo "Waiting for the dashboard..."
ready=false
for _ in {1..60}; do
  if curl --location --max-redirs 3 --fail --silent --show-error --max-time 2 \
      "http://${UNO_HEALTH_AUTHORITY}:8088/status" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done

if [[ "${ready}" != true ]]; then
  echo "error: the UNO Q app did not become ready at http://${UNO_HOST}:8088" >&2
  exit 1
fi

curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
  "http://${UNO_HEALTH_AUTHORITY}:8088/dashboard" >/dev/null
PLAY_HTML="$(curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
  "http://${UNO_HEALTH_AUTHORITY}:8088/play")"
if [[ "${PLAY_HTML}" != *"Rock Paper Scissors"* || "${PLAY_HTML}" != *"data-src=/stream"* ]]; then
  echo "error: deployed Play page is incomplete" >&2
  exit 1
fi
curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
  "http://${UNO_HEALTH_AUTHORITY}:8088/learn" >/dev/null
curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
  "http://${UNO_HEALTH_AUTHORITY}:8088/help" >/dev/null
for HELP_SLUG in build-your-own input-modes troubleshooting cabinet installation gameplay camera configuration security components contributing changelog input-audit engineering-journey engineering-toolkit; do
  curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
    "http://${UNO_HEALTH_AUTHORITY}:8088/help/${HELP_SLUG}" >/dev/null
done
for PDF_SLUG in build-your-own input-modes troubleshooting overview installation gameplay camera configuration security components contributing changelog input-audit engineering-journey engineering-toolkit; do
  curl --location --max-redirs 3 --fail --silent --show-error --max-time 15 \
    "http://${UNO_HEALTH_AUTHORITY}:8088/help-pdf/${PDF_SLUG}.pdf" >/dev/null
done
if curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
    "http://${UNO_HEALTH_AUTHORITY}:8088/help-pdf/quick-reference.pdf" >/dev/null 2>&1; then
  echo "error: cabinet-specific quick-reference PDF was exposed" >&2
  exit 1
fi
curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
  "http://${UNO_HEALTH_AUTHORITY}:8088/help-assets/gestures/actions/v-sign.png" >/dev/null
GAMEPLAY_MARKDOWN="$(curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
  "http://${UNO_HEALTH_AUTHORITY}:8088/help/gameplay.md")"
if [[ "${GAMEPLAY_MARKDOWN}" != *"Take VirtualGlove off-script"* ]]; then
  echo "error: deployed gameplay Help is not the current edition" >&2
  exit 1
fi
GAMEPLAY_HTML="$(curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
  "http://${UNO_HEALTH_AUTHORITY}:8088/help/gameplay")"
for EXPECTED_IMAGE in v2/v-sign.png v2/thumbs-up.png v2/curl-index.png v2/wrist-roll-left.png v2/push-toward-camera.png v2/pixel-pal-ready.png actions/finger-curl.png actions/close-all-fingers.png actions/wrist-roll.png; do
  if [[ "${GAMEPLAY_HTML}" != *"/help-assets/gestures/${EXPECTED_IMAGE}"* ]]; then
    echo "error: gameplay Help is missing ${EXPECTED_IMAGE}" >&2
    exit 1
  fi
done
if [[ "${GAMEPLAY_HTML}" != *"<img loading=lazy"* ]]; then
  echo "error: Help table illustrations were not rendered" >&2
  exit 1
fi
if curl --location --max-redirs 0 --fail --silent --show-error --max-time 5 \
    "http://${UNO_HEALTH_AUTHORITY}:8088/help/programs" >/dev/null 2>&1; then
  echo "error: retired Help alias /help/programs is still available" >&2
  exit 1
fi
curl --insecure --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
  "https://${UNO_HEALTH_AUTHORITY}:8443/setup" >/dev/null

for PAL_PAGE in dashboard play learn setup help; do
  case "${PAL_PAGE}" in
    play) PAL_IMAGE="pixel-pal-ready.png" ;;
    learn) PAL_IMAGE="pixel-pal-coach.png" ;;
    setup) PAL_IMAGE="pixel-pal-thinking.png" ;;
    *) PAL_IMAGE="pixel-pal-web.png" ;;
  esac
  PAL_HTML="$(curl --location --max-redirs 3 --fail --silent --show-error --max-time 5 \
    "http://${UNO_HEALTH_AUTHORITY}:8088/${PAL_PAGE}")"
  if [[ "${PAL_HTML}" != *"/help-assets/gestures/v2/${PAL_IMAGE}"* ]]; then
    echo "error: ${PAL_PAGE} is missing its ${PAL_IMAGE} Pixel Pal pose" >&2
    exit 1
  fi
done
for PAL_IMAGE in pixel-pal-web.png pixel-pal-coach.png pixel-pal-ready.png pixel-pal-thinking.png pixel-pal-safety.png pixel-pal-success.png pixel-pal-gold-cup.png; do
  curl --location --max-redirs 3 --fail --silent --show-error --max-time 10 \
    "http://${UNO_HEALTH_AUTHORITY}:8088/help-assets/gestures/v2/${PAL_IMAGE}" >/dev/null
done

CONTAINERS="$(ssh "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
  "docker ps --format '{{.Names}}'")"
for EXPECTED_CONTAINER in virtualglove-main-1 virtualglove-profile-relay-1 virtualglove-avahi-resolver-1; do
  if [[ "${CONTAINERS}" != *"${EXPECTED_CONTAINER}"* ]]; then
    echo "error: expected container ${EXPECTED_CONTAINER} is not running" >&2
    exit 1
  fi
done
echo "Deployment complete."
echo "  Play:   http://${UNO_HOST}:8088/play"
echo "  Learn:  http://${UNO_HOST}:8088/learn"
echo "  Dashboard:  http://${UNO_HOST}:8088/dashboard"
echo "  Help:   http://${UNO_HOST}:8088/help"
echo "  Setup:  https://${UNO_HOST}:8443/setup"
if [[ "${PRIVILEGED_READY}" != true ]]; then
  echo "Run this directly in an UNO Q terminal only if host helpers or Matrix firmware changed:"
  echo "  cd '${REMOTE_APP_DIR}'"
  echo "  sudo python3 scripts/setup-machine.py uno-q --runtime-names-only"
  echo "  sudo python3 scripts/flash-matrix-firmware.py firmware/matrix"
fi
