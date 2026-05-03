#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="/srv/ageo-deploy"
LEGACY_ROOT="/srv/ageo"
REPO_URL="git@github.com:nooqle/AGEO.git"
TARGET_REF=""
EXTERNAL_URL="https://demo.imspecta.com"
BACKEND_SERVICE="ageo-backend.service"
FRONTEND_SERVICE="ageo-frontend.service"
DRY_RUN=0
ROLLBACK=0
ALLOW_MIGRATIONS=0
MIGRATIONS_CHANGED=0

usage() {
  cat <<'EOF'
Usage:
  deploy-demo.sh --sha <commit-ish> [--repo <repo-url>] [--external-url <url>] [--root <path>] [--dry-run]
  deploy-demo.sh --sha <commit-ish> --allow-migrations [--repo <repo-url>] [--external-url <url>] [--root <path>]
  deploy-demo.sh --rollback [--root <path>] [--external-url <url>]

Deploys AGEO demo from a git commit into an isolated release directory, then
atomically switches /srv/ageo-deploy/current and restarts systemd services.
EOF
}

log() {
  printf '[deploy-demo] %s\n' "$*" >&2
}

fail() {
  printf '[deploy-demo] ERROR: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sha)
      TARGET_REF="${2:-}"
      shift 2
      ;;
    --repo)
      REPO_URL="${2:-}"
      shift 2
      ;;
    --external-url)
      EXTERNAL_URL="${2:-}"
      shift 2
      ;;
    --root)
      APP_ROOT="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --allow-migrations)
      ALLOW_MIGRATIONS=1
      shift
      ;;
    --rollback)
      ROLLBACK=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

if [[ "$ROLLBACK" -eq 0 && -z "$TARGET_REF" ]]; then
  fail "--sha is required unless --rollback is used"
fi

if [[ "$ROLLBACK" -eq 1 && -n "$TARGET_REF" ]]; then
  fail "--rollback cannot be combined with --sha"
fi

if [[ "$APP_ROOT" != /srv/* ]]; then
  fail "--root must stay under /srv for this deployment script"
fi

REPO_DIR="$APP_ROOT/repo.git"
RELEASES_DIR="$APP_ROOT/releases"
SHARED_DIR="$APP_ROOT/shared"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
LOCK_FILE="$APP_ROOT/deploy.lock"
BACKEND_ENV="$SHARED_DIR/backend/.env.local"
FRONTEND_ENV="$SHARED_DIR/frontend/.env.local"
PIP_CACHE_DIR="$SHARED_DIR/pip-cache"
NPM_CACHE_DIR="$SHARED_DIR/npm-cache"
RUNTIME_DIR="$SHARED_DIR/runtime"
UPLOAD_DIR="$SHARED_DIR/uploads"
FAILURE_EVIDENCE_DIR="$RUNTIME_DIR/failure-evidence"

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

sudo_write_file() {
  local target="$1"
  local tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  sudo install -m 0644 "$tmp" "$target"
  rm -f "$tmp"
}

backup_existing_units() {
  local backup_dir="$APP_ROOT/service-backups/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$backup_dir"

  for service in "$BACKEND_SERVICE" "$FRONTEND_SERVICE"; do
    local unit_path="/etc/systemd/system/$service"
    local dropin_path="/etc/systemd/system/$service.d"
    if [[ -e "$unit_path" ]]; then
      sudo cp -a "$unit_path" "$backup_dir/$service"
    fi
    if [[ -d "$dropin_path" ]]; then
      sudo cp -a "$dropin_path" "$backup_dir/$service.d"
    fi
  done
  sudo chown -R "$(id -u):$(id -g)" "$backup_dir"
  printf '%s\n' "$backup_dir"
}

restore_units_from_backup() {
  local backup_dir="$1"
  [[ -d "$backup_dir" ]] || fail "Service backup directory is missing: $backup_dir"

  log "Restoring systemd units from $backup_dir"
  for service in "$BACKEND_SERVICE" "$FRONTEND_SERVICE"; do
    sudo rm -f "/etc/systemd/system/$service"
    sudo rm -rf "/etc/systemd/system/$service.d"
    if [[ -e "$backup_dir/$service" ]]; then
      sudo cp -a "$backup_dir/$service" "/etc/systemd/system/$service"
    fi
    if [[ -d "$backup_dir/$service.d" ]]; then
      sudo cp -a "$backup_dir/$service.d" "/etc/systemd/system/$service.d"
    fi
  done
  sudo systemctl daemon-reload
  sudo systemctl restart "$BACKEND_SERVICE"
  sudo systemctl restart "$FRONTEND_SERVICE"
}

ensure_base_dirs() {
  sudo mkdir -p "$APP_ROOT"
  sudo chown "$(id -u):$(id -g)" "$APP_ROOT"
  mkdir -p \
    "$RELEASES_DIR" \
    "$SHARED_DIR/backend" \
    "$SHARED_DIR/frontend" \
    "$PIP_CACHE_DIR" \
    "$NPM_CACHE_DIR" \
    "$RUNTIME_DIR" \
    "$UPLOAD_DIR" \
    "$FAILURE_EVIDENCE_DIR"
}

acquire_lock() {
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "Another deployment is already running"
}

bootstrap_shared_env() {
  if [[ ! -f "$BACKEND_ENV" && -f "$LEGACY_ROOT/aeo-platform/backend/.env.local" ]]; then
    log "Bootstrapping backend .env.local from legacy deployment"
    sudo cp "$LEGACY_ROOT/aeo-platform/backend/.env.local" "$BACKEND_ENV"
    sudo chown "$(id -u):$(id -g)" "$BACKEND_ENV"
    chmod 600 "$BACKEND_ENV"
  fi

  if [[ ! -f "$FRONTEND_ENV" && -f "$LEGACY_ROOT/frontend/.env.local" ]]; then
    log "Bootstrapping frontend .env.local from legacy deployment"
    sudo cp "$LEGACY_ROOT/frontend/.env.local" "$FRONTEND_ENV"
    sudo chown "$(id -u):$(id -g)" "$FRONTEND_ENV"
    chmod 600 "$FRONTEND_ENV"
  fi

  [[ -f "$BACKEND_ENV" ]] || fail "Missing backend env file: $BACKEND_ENV"
}

prepare_repo() {
  if [[ ! -d "$REPO_DIR" ]]; then
    log "Initializing bare git mirror"
    git init --bare "$REPO_DIR" >/dev/null
  fi

  if [[ "$REPO_URL" == git@github.com:* || "$REPO_URL" == ssh://git@github.com/* ]]; then
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"
    touch "$HOME/.ssh/known_hosts"
    chmod 600 "$HOME/.ssh/known_hosts"
    if command -v ssh-keygen >/dev/null 2>&1 && command -v ssh-keyscan >/dev/null 2>&1; then
      if ! ssh-keygen -F github.com >/dev/null 2>&1; then
        log "Adding github.com to SSH known_hosts"
        ssh-keyscan github.com >> "$HOME/.ssh/known_hosts"
      fi
    fi
  fi

  if git --git-dir="$REPO_DIR" remote get-url origin >/dev/null 2>&1; then
    git --git-dir="$REPO_DIR" remote set-url origin "$REPO_URL"
  else
    git --git-dir="$REPO_DIR" remote add origin "$REPO_URL"
  fi

  log "Fetching repository refs"
  git --git-dir="$REPO_DIR" fetch --prune --tags origin \
    '+refs/heads/*:refs/remotes/origin/*' \
    '+refs/tags/*:refs/tags/*'
}

resolve_target_sha() {
  local ref="$1"
  local resolved=""
  if resolved="$(git --git-dir="$REPO_DIR" rev-parse --verify "${ref}^{commit}" 2>/dev/null)"; then
    :
  elif resolved="$(git --git-dir="$REPO_DIR" rev-parse --verify "origin/${ref}^{commit}" 2>/dev/null)"; then
    :
  else
    fail "Could not resolve deploy ref: $ref"
  fi
  printf '%s\n' "$resolved"
}

current_sha() {
  if [[ -L "$CURRENT_LINK" && -f "$CURRENT_LINK/.release-sha" ]]; then
    tr -d '[:space:]' < "$CURRENT_LINK/.release-sha"
  else
    printf ''
  fi
}

guard_migrations() {
  local from_sha="$1"
  local to_sha="$2"
  if [[ -z "$from_sha" || "$from_sha" == "$to_sha" ]]; then
    return 0
  fi

  local changed
  changed="$(git --git-dir="$REPO_DIR" diff --name-only "$from_sha" "$to_sha" -- 'aeo-platform/backend/alembic/versions/' || true)"
  if [[ -n "$changed" ]]; then
    if [[ "$ALLOW_MIGRATIONS" -eq 1 ]]; then
      MIGRATIONS_CHANGED=1
      log "Alembic migration files changed and explicit migration execution is enabled"
      printf '%s\n' "$changed" >&2
      return 0
    fi
    printf '[deploy-demo] migration_required\n' >&2
    printf '%s\n' "$changed" >&2
    fail "Alembic migration files changed; first-version demo deploy will not run migrations automatically"
  fi
}

run_backend_migrations() {
  local release_dir="$1"
  local backend_dir="$release_dir/aeo-platform/backend"

  log "Running backend database migrations"
  (
    cd "$backend_dir"
    "$backend_dir/.venv/bin/alembic" upgrade head
  )
}

create_release_tree() {
  local sha="$1"
  local release_dir="$RELEASES_DIR/$sha"

  if [[ "$release_dir" != "$RELEASES_DIR/"* ]]; then
    fail "Resolved release directory escaped releases root"
  fi

  rm -rf "$release_dir"
  mkdir -p "$release_dir"
  log "Exporting git archive to $release_dir"
  git --git-dir="$REPO_DIR" archive "$sha" | tar -x -C "$release_dir"
  printf '%s\n' "$sha" > "$release_dir/.release-sha"
  printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$release_dir/.release-created-at"

  ln -sfn "$BACKEND_ENV" "$release_dir/aeo-platform/backend/.env.local"
  if [[ -f "$FRONTEND_ENV" ]]; then
    ln -sfn "$FRONTEND_ENV" "$release_dir/frontend/.env.local"
  fi
  rm -rf "$release_dir/aeo-platform/backend/uploads"
  ln -sfn "$UPLOAD_DIR" "$release_dir/aeo-platform/backend/uploads"
  ln -sfn "$RUNTIME_DIR" "$release_dir/runtime"

  printf '%s\n' "$release_dir"
}

build_backend() {
  local release_dir="$1"
  local backend_dir="$release_dir/aeo-platform/backend"

  log "Building backend virtualenv"
  python3 -m venv "$backend_dir/.venv"
  "$backend_dir/.venv/bin/python" -m pip install --upgrade pip
  "$backend_dir/.venv/bin/python" -m pip install \
    --cache-dir "$PIP_CACHE_DIR" \
    -r "$backend_dir/requirements.txt"

  log "Compiling backend Python sources"
  (
    cd "$backend_dir"
    "$backend_dir/.venv/bin/python" -m compileall app
  )
}

build_frontend() {
  local release_dir="$1"
  local frontend_dir="$release_dir/frontend"

  log "Installing and building frontend"
  (
    cd "$frontend_dir"
    npm ci --cache "$NPM_CACHE_DIR"
    npm run build
  )
}

install_systemd_units() {
  local current_backend="$CURRENT_LINK/aeo-platform/backend"
  local current_frontend="$CURRENT_LINK/frontend"

  log "Installing systemd units"
  sudo_write_file "/etc/systemd/system/$BACKEND_SERVICE" <<EOF
[Unit]
Description=AGEO Backend
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
WorkingDirectory=$current_backend
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:99
Environment=PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
Environment=UPLOAD_DIR=$UPLOAD_DIR
Environment=A4_FAILURE_EVIDENCE_DIR=$FAILURE_EVIDENCE_DIR
ExecStart=$current_backend/.venv/bin/uvicorn app.main:socket_app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  sudo_write_file "/etc/systemd/system/$FRONTEND_SERVICE" <<EOF
[Unit]
Description=AGEO Frontend
After=network.target $BACKEND_SERVICE

[Service]
Type=simple
WorkingDirectory=$current_frontend
Environment=NODE_ENV=production
ExecStart=/usr/bin/npm run start -- --hostname 0.0.0.0 --port 3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable "$BACKEND_SERVICE" "$FRONTEND_SERVICE" >/dev/null
}

switch_current() {
  local release_dir="$1"
  local old_current=""

  if [[ -L "$CURRENT_LINK" ]]; then
    old_current="$(readlink -f "$CURRENT_LINK" || true)"
  fi

  if [[ -n "$old_current" && -d "$old_current" ]]; then
    ln -sfn "$old_current" "$PREVIOUS_LINK.next"
    mv -Tf "$PREVIOUS_LINK.next" "$PREVIOUS_LINK"
  fi

  ln -sfn "$release_dir" "$CURRENT_LINK.next"
  mv -Tf "$CURRENT_LINK.next" "$CURRENT_LINK"
}

restart_services() {
  log "Restarting services"
  local status=0
  sudo systemctl restart "$BACKEND_SERVICE" || status=1
  sudo systemctl restart "$FRONTEND_SERVICE" || status=1
  return "$status"
}

wait_for_url() {
  local label="$1"
  local url="$2"
  local max_attempts="${3:-30}"
  local attempt

  for attempt in $(seq 1 "$max_attempts"); do
    if curl -k -fsS --max-time 10 "$url" >/dev/null; then
      log "$label is healthy"
      return 0
    fi
    sleep 2
  done
  return 1
}

dump_service_diagnostics() {
  local service
  for service in "$BACKEND_SERVICE" "$FRONTEND_SERVICE"; do
    log "systemd status for $service"
    sudo systemctl status "$service" --no-pager --lines=40 || true
    log "journal tail for $service"
    sudo journalctl -u "$service" --no-pager -n 160 || true
  done
}

health_check() {
  local status=0
  local backend_attempts="${BACKEND_HEALTH_ATTEMPTS:-120}"
  log "Running health checks"
  systemctl is-active "$BACKEND_SERVICE" >/dev/null || status=1
  systemctl is-active "$FRONTEND_SERVICE" >/dev/null || status=1
  wait_for_url "backend" "http://127.0.0.1:8000/health" "$backend_attempts" || status=1
  wait_for_url "frontend" "http://127.0.0.1:3000" 30 || status=1
  wait_for_url "external" "$EXTERNAL_URL" 15 || status=1
  return "$status"
}

rollback_to_previous() {
  [[ -L "$PREVIOUS_LINK" ]] || fail "No previous release symlink exists"
  local previous_target
  local old_current=""
  previous_target="$(readlink -f "$PREVIOUS_LINK")"
  [[ -d "$previous_target" ]] || fail "Previous release target is missing: $previous_target"

  if [[ -L "$CURRENT_LINK" ]]; then
    old_current="$(readlink -f "$CURRENT_LINK" || true)"
  fi

  log "Rolling back to $previous_target"
  ln -sfn "$previous_target" "$CURRENT_LINK.next"
  mv -Tf "$CURRENT_LINK.next" "$CURRENT_LINK"

  if [[ -n "$old_current" && -d "$old_current" && "$old_current" != "$previous_target" ]]; then
    ln -sfn "$old_current" "$PREVIOUS_LINK.next"
    mv -Tf "$PREVIOUS_LINK.next" "$PREVIOUS_LINK"
  fi

  install_systemd_units
  restart_services
  health_check
  log "Rollback complete"
}

deploy() {
  require_command git
  require_command tar
  require_command python3
  require_command npm
  require_command curl
  require_command flock
  require_command sudo

  ensure_base_dirs
  acquire_lock

  if [[ "$ROLLBACK" -eq 1 ]]; then
    rollback_to_previous
    return
  fi

  bootstrap_shared_env
  prepare_repo

  local sha
  local old_sha
  local release_dir
  local service_backup_dir
  sha="$(resolve_target_sha "$TARGET_REF")"
  old_sha="$(current_sha)"
  log "Resolved target: $sha"
  guard_migrations "$old_sha" "$sha"
  release_dir="$(create_release_tree "$sha")"

  build_backend "$release_dir"
  build_frontend "$release_dir"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "Dry-run complete; built $release_dir without switching systemd"
    return
  fi

  if [[ "$MIGRATIONS_CHANGED" -eq 1 ]]; then
    run_backend_migrations "$release_dir"
  fi

  service_backup_dir="$(backup_existing_units)"
  switch_current "$release_dir"
  install_systemd_units

  if ! restart_services || ! health_check; then
    dump_service_diagnostics
    log "Deployment health check failed; attempting rollback"
    if [[ -L "$PREVIOUS_LINK" ]]; then
      rollback_to_previous
    else
      restore_units_from_backup "$service_backup_dir"
      health_check || fail "Restored legacy services, but legacy health checks failed"
    fi
    fail "Deployment failed health checks"
  fi

  log "Deployment complete: $sha"
}

deploy
