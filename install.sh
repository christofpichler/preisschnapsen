#!/usr/bin/env bash
# Install or update Preisschnapsen on Debian 12 / Ubuntu 24.04. Run as root from the repository directory.
# Idempotent: data and passwords are kept when run again.
#
# Overridable via environment variables (for tests and special setups):
#   APP_DIR DATA_DIR CONF_FILE BIN_DIR UNIT_DIR SKIP_APT=1 SKIP_SYSTEMD=1 SKIP_USER=1
#   INSTALL_ADMIN_PASSWORD INSTALL_DASHBOARD_PASSWORD (non-interactive installation)
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/schnapsen}"
DATA_DIR="${DATA_DIR:-/var/lib/schnapsen}"
CONF_FILE="${CONF_FILE:-/etc/schnapsen/schnapsen.env}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"
SVC_USER="schnapsen"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Please run as root (sudo ./install.sh)."
[ -d "$SRC/app" ] && [ -f "$SRC/requirements.txt" ] || die "Please run from the repository directory."

if [ "${SKIP_APT:-0}" != "1" ]; then
  say "Installing system packages (python3, python3-venv); internet access is required once"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv ca-certificates
fi

if [ "${SKIP_USER:-0}" != "1" ]; then
  if ! getent group "$SVC_USER" >/dev/null; then groupadd --system "$SVC_USER"; fi
  if ! id "$SVC_USER" >/dev/null 2>&1; then
    say "Creating system user '$SVC_USER'"
    useradd --system --gid "$SVC_USER" --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SVC_USER"
  fi
  OWNER="$SVC_USER:$SVC_USER"
else
  OWNER="$(id -un):$(id -gn)"
fi

say "Copying application files to $APP_DIR"
mkdir -p "$APP_DIR"
rm -rf "${APP_DIR:?}/app"
cp -r "$SRC/app" "$APP_DIR/app"
cp "$SRC/requirements.txt" "$APP_DIR/requirements.txt"
find "$APP_DIR/app" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

say "Setting up the Python environment"
[ -x "$APP_DIR/venv/bin/python" ] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --disable-pip-version-check -q --upgrade pip >/dev/null 2>&1 || true
"$APP_DIR/venv/bin/pip" install --disable-pip-version-check -q -r "$APP_DIR/requirements.txt"

say "Preparing data directory $DATA_DIR and configuration $CONF_FILE"
mkdir -p "$DATA_DIR/backups"
chown -R "$OWNER" "$DATA_DIR"
chmod 750 "$DATA_DIR"
mkdir -p "$(dirname "$CONF_FILE")"
if [ ! -f "$CONF_FILE" ]; then
  cp "$SRC/.env.example" "$CONF_FILE"
  sed -i "s#^SCHNAPSEN_DB=.*#SCHNAPSEN_DB=$DATA_DIR/schnapsen.db#; s#^SCHNAPSEN_BACKUP_DIR=.*#SCHNAPSEN_BACKUP_DIR=$DATA_DIR/backups#" "$CONF_FILE"
fi
if [ "${SKIP_USER:-0}" != "1" ]; then chown "root:$SVC_USER" "$CONF_FILE"; fi
chmod 640 "$CONF_FILE"

PY="$APP_DIR/venv/bin/python"
has_hash() { grep -Eq "^$1=.+" "$CONF_FILE"; }

ask_password() {  # $1 = label, $2 = admin|dashboard, $3 = default user name, $4 = env variable holding the password
  local label="$1" which="$2" defuser="$3" envpw="${!4:-}" user pw pw2
  if [ -n "$envpw" ]; then
    user="$defuser"; pw="$envpw"
  else
    [ -t 0 ] || die "No terminal for the password prompt. Set INSTALL_ADMIN_PASSWORD and INSTALL_DASHBOARD_PASSWORD or run interactively."
    read -r -p "User name for $label [$defuser]: " user
    user="${user:-$defuser}"
    while true; do
      read -r -s -p "Password for $label (min. 6 characters): " pw; echo
      read -r -s -p "Repeat password: " pw2; echo
      if [ "${#pw}" -lt 6 ]; then echo "Too short."; continue; fi
      if [ "$pw" != "$pw2" ]; then echo "The entries do not match."; continue; fi
      break
    done
  fi
  printf '%s\n' "$pw" | "$PY" -m app.cli --config "$CONF_FILE" passwd "$which" --stdin --user "$user" >/dev/null
  echo "  Account '$label' ($user) set."
}

cd "$APP_DIR"
if ! has_hash SCHNAPSEN_ADMIN_HASH; then
  say "Set the admin account"
  ask_password "Admin" admin admin INSTALL_ADMIN_PASSWORD
fi
if ! has_hash SCHNAPSEN_DASHBOARD_HASH; then
  say "Set the account for the user role (dashboard only)"
  ask_password "user" dashboard user INSTALL_DASHBOARD_PASSWORD
fi
if [ "${SKIP_USER:-0}" != "1" ]; then chown "root:$SVC_USER" "$CONF_FILE"; fi
chmod 640 "$CONF_FILE"

say "Creating helper commands $BIN_DIR/schnapsen-passwd and $BIN_DIR/schnapsen"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/schnapsen-passwd" <<WRAP
#!/bin/sh
# Set a password: schnapsen-passwd admin | schnapsen-passwd user (alias: dashboard)
[ "\$(id -u)" -eq 0 ] || { echo "Please run as root." >&2; exit 1; }
cd "$APP_DIR" || exit 1
SCHNAPSEN_CONFIG="$CONF_FILE" "$PY" -m app.cli passwd "\$@" || exit \$?
systemctl try-restart schnapsen 2>/dev/null || true
WRAP
cat > "$BIN_DIR/schnapsen" <<WRAP
#!/bin/sh
# Management command: schnapsen demo | simulate | backup | hash
cd "$APP_DIR" || exit 1
export SCHNAPSEN_CONFIG="$CONF_FILE"
if [ "\$(id -u)" -eq 0 ] && id $SVC_USER >/dev/null 2>&1 && command -v runuser >/dev/null 2>&1; then
  exec runuser -u $SVC_USER -- "$PY" -m app.cli "\$@"
fi
exec "$PY" -m app.cli "\$@"
WRAP
chmod 755 "$BIN_DIR/schnapsen-passwd" "$BIN_DIR/schnapsen"

PORT="$(grep -E '^SCHNAPSEN_PORT=' "$CONF_FILE" | tail -1 | cut -d= -f2)"; PORT="${PORT:-8080}"
if [ "${SKIP_SYSTEMD:-0}" != "1" ]; then
  say "Installing and starting the systemd service"
  install -m 644 "$SRC/deploy/schnapsen.service" "$UNIT_DIR/schnapsen.service"
  systemctl daemon-reload
  systemctl enable schnapsen >/dev/null 2>&1 || true
  # cancel stuck start jobs of a previous attempt (e.g. waiting for network-online)
  systemctl list-jobs --no-legend 2>/dev/null \
    | awk '$2=="schnapsen.service" || $2=="network-online.target" {print $1}' \
    | xargs -r systemctl cancel 2>/dev/null || true

  # Start the service without blocking and wait up to 45 s until the port answers
  # (an old running process may need up to TimeoutStopSec to stop).
  start_service() {
    systemctl reset-failed schnapsen >/dev/null 2>&1 || true
    systemctl restart --no-block schnapsen
    local i
    for i in $(seq 1 45); do
      sleep 1
      if systemctl is-active --quiet schnapsen && (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
        return 0
      fi
    done
    return 1
  }

  if ! start_service; then
    if journalctl -u schnapsen -n 60 --no-pager 2>/dev/null | grep -qE '226/NAMESPACE|status=226|mount namespac'; then
      say "systemd sandboxing is not available in this container; starting without sandbox options"
      mkdir -p "$UNIT_DIR/schnapsen.service.d"
      cat > "$UNIT_DIR/schnapsen.service.d/container.conf" <<'DROPIN'
# Created by install.sh: mount namespaces are unavailable in this container
# (e.g. an unprivileged LXC without "nesting").
[Service]
ProtectSystem=no
ProtectHome=no
PrivateTmp=no
PrivateDevices=no
ProtectKernelTunables=no
ProtectKernelModules=no
ProtectControlGroups=no
ReadWritePaths=
DROPIN
      systemctl daemon-reload
      start_service || true
    fi
  fi
  if ! systemctl is-active --quiet schnapsen; then
    systemctl status schnapsen --no-pager -l 2>/dev/null | head -20 || true
    journalctl -u schnapsen -n 30 --no-pager || true
    die "The service is not running. See the log above (journalctl -u schnapsen)."
  fi
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-<host-ip>}"
say "Done."
echo "  Dashboard: http://$IP:$PORT/dashboard/"
echo "  Admin:     http://$IP:$PORT/admin/"
echo "  Change a password: schnapsen-passwd admin   |   schnapsen-passwd user"
echo "  Demo tournament:   schnapsen demo   (creates and activates a sample tournament)"
