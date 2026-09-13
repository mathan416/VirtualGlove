#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/install-uno-q-camera-recovery-helper.sh
# Purpose: Install only the fixed-purpose UNO Q USB camera recovery helper.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Installed uhubctl for supported per-port camera power cycling.
#   2026-09-05 - Added a camera-only installer separate from shutdown privileges.
# Full history: docs/CHANGELOG.md and Git history.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly UNO_TARGET="${1:-${UNO_Q_SSH_TARGET:-arduino@arduiain.local}}"
readonly REMOTE_APP_DIR="/home/arduino/ArduinoApps/virtualglove"
readonly REMOTE_PATH_UNIT="/tmp/virtualglove-camera-recovery.path"
readonly REMOTE_SERVICE_UNIT="/tmp/virtualglove-camera-recovery.service"
readonly REMOTE_HELPER="/tmp/virtualglove-camera-recovery"
readonly REMOTE_TMPFILES_CONFIG="/tmp/virtualglove-camera-recovery.conf"
SSH_OPTIONS=()

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'USAGE'
Usage: scripts/install-uno-q-camera-recovery-helper.sh [user@uno-q-host]

Install the fixed-purpose, root-owned recovery helper for one UVC camera. A
connected camera and its parent hub are enrolled now; otherwise enrollment is
deferred until VirtualGlove first sees the camera.
The remote sudo command prompts for the UNO Q account password. No password is
read or stored by this script.
USAGE
  exit 0
fi

if [[ $# -gt 1 || "${UNO_TARGET}" == -* || "${UNO_TARGET}" =~ [[:space:]\'] ]]; then
  echo "error: expected one user@host SSH destination" >&2
  exit 2
fi
if [[ -n "${UNO_Q_SSH_IDENTITY:-}" ]]; then
  [[ -f "${UNO_Q_SSH_IDENTITY}" ]] || { echo "error: UNO_Q_SSH_IDENTITY is not a file" >&2; exit 2; }
  SSH_OPTIONS=(-i "${UNO_Q_SSH_IDENTITY}")
fi

scp "${SSH_OPTIONS[@]}" "${PROJECT_DIR}/uno-q/virtualglove-camera-recovery.path" "${UNO_TARGET}:${REMOTE_PATH_UNIT}"
scp "${SSH_OPTIONS[@]}" "${PROJECT_DIR}/uno-q/virtualglove-camera-recovery.service" "${UNO_TARGET}:${REMOTE_SERVICE_UNIT}"
scp "${SSH_OPTIONS[@]}" "${PROJECT_DIR}/uno-q/virtualglove-camera-recovery.py" "${UNO_TARGET}:${REMOTE_HELPER}"
scp "${SSH_OPTIONS[@]}" "${PROJECT_DIR}/uno-q/virtualglove-camera-recovery.conf" "${UNO_TARGET}:${REMOTE_TMPFILES_CONFIG}"

ssh -t "${SSH_OPTIONS[@]}" "${UNO_TARGET}" \
  "sudo apt-get update && \
   sudo apt-get install -y uhubctl && \
   sudo install -m 0644 '${REMOTE_PATH_UNIT}' /etc/systemd/system/virtualglove-camera-recovery.path && \
   sudo install -m 0644 '${REMOTE_SERVICE_UNIT}' /etc/systemd/system/virtualglove-camera-recovery.service && \
   sudo install -m 0755 '${REMOTE_HELPER}' /usr/local/libexec/virtualglove-camera-recovery && \
   sudo install -m 0644 '${REMOTE_TMPFILES_CONFIG}' /etc/tmpfiles.d/virtualglove-camera-recovery.conf && \
   sudo /usr/local/libexec/virtualglove-camera-recovery --configure-if-present && \
   sudo systemctl daemon-reload && \
   sudo systemctl enable --now virtualglove-camera-recovery.path && \
   sudo systemd-tmpfiles --create /etc/tmpfiles.d/virtualglove-camera-recovery.conf && \
   rm -f '${REMOTE_PATH_UNIT}' '${REMOTE_SERVICE_UNIT}' '${REMOTE_HELPER}' '${REMOTE_TMPFILES_CONFIG}' && \
   mkdir -p '${REMOTE_APP_DIR}/data' && touch '${REMOTE_APP_DIR}/data/.camera-recovery-enabled' && \
   systemctl is-enabled virtualglove-camera-recovery.path && \
   systemctl is-active virtualglove-camera-recovery.path"

echo "UNO Q camera-recovery helper installed."
