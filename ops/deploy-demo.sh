#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="/srv/ageo-deploy"
LEGACY_ROOT="/srv/ageo"
REPO_URL="git@github.com:nooqle/AGEO.git"
TARGET_REF=""
EXTERNAL_URL="https://imspecta.com"
DOMAIN_REDIRECT_HOSTS="${DOMAIN_REDIRECT_HOSTS:-demo.imspecta.com www.imspecta.com}"
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

external_url_host() {
  python3 - "$EXTERNAL_URL" <<'PY'
import sys
from urllib.parse import urlparse

value = sys.argv[1].strip()
parsed = urlparse(value if "://" in value else f"https://{value}")
host = parsed.netloc or parsed.path
if not host:
    raise SystemExit("external URL host is empty")
print(host.split("@")[-1].split(":")[0])
PY
}

sync_public_domain_env() {
  log "Synchronizing public domain environment"
  python3 - "$FRONTEND_ENV" "$BACKEND_ENV" "$EXTERNAL_URL" "$DOMAIN_REDIRECT_HOSTS" "$RUNTIME_DIR" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

frontend_env = Path(sys.argv[1])
backend_env = Path(sys.argv[2])
external_url = sys.argv[3].strip().rstrip("/")
redirect_hosts = [host.strip() for host in sys.argv[4].split() if host.strip()]
runtime_dir = Path(sys.argv[5])

parsed = urlparse(external_url if "://" in external_url else f"https://{external_url}")
scheme = parsed.scheme or "https"
host = (parsed.netloc or parsed.path).split("@")[-1].split(":")[0]
origin = f"{scheme}://{host}"
api_url = f"{origin}/api/v1"
ws_scheme = "wss" if scheme == "https" else "ws"
ws_url = f"{ws_scheme}://{host}"


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def upsert(path: Path, key: str, value: str) -> None:
    lines = read_lines(path)
    prefix = f"{key}="
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            output.append(f"{key}={value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def current_env_value(path: Path, key: str) -> str:
    prefix = f"{key}="
    for line in read_lines(path):
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip("'\"")
    return ""


def parse_origins(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
        except json.JSONDecodeError:
            pass
    return [item.strip().strip("'\"") for item in raw.split(",") if item.strip()]


upsert(frontend_env, "NEXT_PUBLIC_API_URL", api_url)
upsert(frontend_env, "NEXT_PUBLIC_WS_URL", ws_url)
upsert(frontend_env, "NEXT_PUBLIC_BRAND_SPACE_ENABLED", "true")
upsert(
    backend_env,
    "BRAND_SPACE_ASSET_STORAGE_ROOT",
    str(runtime_dir / "brand-space-assets"),
)

origins = parse_origins(current_env_value(backend_env, "CORS_ORIGINS"))
for item in [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    origin,
    *(f"https://{host}" for host in redirect_hosts),
]:
    if item not in origins:
        origins.append(item)
upsert(
    backend_env,
    "CORS_ORIGINS",
    json.dumps(origins, ensure_ascii=False, separators=(",", ":")),
)
PY
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
    "$RUNTIME_DIR/brand-space-assets" \
    "$UPLOAD_DIR" \
    "$FAILURE_EVIDENCE_DIR"
}

acquire_lock() {
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "Another deployment is already running"
}

prune_deploy_workspace() {
  local current_target=""
  local previous_target=""
  local release=""
  local resolved=""

  log "Pruning deploy workspace before build"
  df -h "$APP_ROOT" >&2 || true

  if [[ -f "$REPO_DIR/config.lock" ]]; then
    log "Removing stale git config lock"
    rm -f "$REPO_DIR/config.lock"
  fi

  if [[ -d "$NPM_CACHE_DIR/_cacache/tmp" ]]; then
    log "Cleaning npm cache temp files"
    sudo find "$NPM_CACHE_DIR/_cacache/tmp" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + || true
  fi

  if [[ -d "$RELEASES_DIR" ]]; then
    current_target="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
    previous_target="$(readlink -f "$PREVIOUS_LINK" 2>/dev/null || true)"

    while IFS= read -r release; do
      [[ -n "$release" && -d "$release" ]] || continue
      resolved="$(readlink -f "$release" 2>/dev/null || true)"
      [[ -n "$resolved" ]] || continue
      if [[ "$resolved" == "$current_target" || "$resolved" == "$previous_target" ]]; then
        continue
      fi
      if [[ "$resolved" != "$RELEASES_DIR/"* ]]; then
        log "Skipping release outside releases root: $resolved"
        continue
      fi
      log "Removing old release: $(basename "$resolved")"
      sudo rm -rf "$resolved"
    done < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -print)
  fi

  df -h "$APP_ROOT" >&2 || true
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

certificate_pair_for_host() {
  local host="$1"
  local candidate
  local cert_dir
  local nginx_pair
  local wildcard=""

  if [[ "$host" == *.* ]]; then
    wildcard="*.${host#*.}"
  fi

  if [[ -f "/etc/letsencrypt/live/$host/fullchain.pem" && -f "/etc/letsencrypt/live/$host/privkey.pem" ]]; then
    printf '/etc/letsencrypt/live/%s/fullchain.pem|/etc/letsencrypt/live/%s/privkey.pem\n' "$host" "$host"
    return 0
  fi

  shopt -s nullglob
  for candidate in /etc/letsencrypt/live/*/fullchain.pem; do
    if sudo openssl x509 -in "$candidate" -noout -ext subjectAltName 2>/dev/null \
      | grep -F "DNS:$host" >/dev/null; then
      cert_dir="$(dirname "$candidate")"
      printf '%s/fullchain.pem|%s/privkey.pem\n' "$cert_dir" "$cert_dir"
      return 0
    fi
    if [[ -n "$wildcard" ]] && sudo openssl x509 -in "$candidate" -noout -ext subjectAltName 2>/dev/null \
      | grep -F "DNS:$wildcard" >/dev/null; then
      cert_dir="$(dirname "$candidate")"
      printf '%s/fullchain.pem|%s/privkey.pem\n' "$cert_dir" "$cert_dir"
      return 0
    fi
  done

  nginx_pair="$(
    sudo nginx -T 2>/dev/null | python3 -c '
import re
import sys

host = sys.argv[1]
text = sys.stdin.read().splitlines()
inside = False
depth = 0
block: list[str] = []

for line in text:
    stripped = line.strip()
    if not inside and re.match(r"server\s*\{", stripped):
        inside = True
        depth = stripped.count("{") - stripped.count("}")
        block = [line]
        continue
    if not inside:
        continue
    block.append(line)
    depth += stripped.count("{") - stripped.count("}")
    if depth > 0:
        continue

    joined = "\n".join(block)
    inside = False
    if not re.search(r"\bserver_name\b[^;]*\b" + re.escape(host) + r"\b", joined):
        continue
    cert = re.search(r"^\s*ssl_certificate\s+([^;]+);", joined, re.MULTILINE)
    key = re.search(r"^\s*ssl_certificate_key\s+([^;]+);", joined, re.MULTILINE)
    if cert and key:
        print(f"{cert.group(1).strip()}|{key.group(1).strip()}")
        raise SystemExit(0)
    ' "$host"
  )"
  if [[ -n "$nginx_pair" ]]; then
    printf '%s\n' "$nginx_pair"
    return 0
  fi

  fail "No TLS certificate pair found for host: $host"
}

install_nginx_site() {
  local primary_host
  local primary_cert_pair
  local primary_cert
  local primary_key
  local redirect_host
  local redirect_cert_pair
  local redirect_cert
  local redirect_key
  local tmp
  local site_path="/etc/nginx/sites-available/00-ageo-domain.conf"
  local enabled_path="/etc/nginx/sites-enabled/00-ageo-domain.conf"

  require_command nginx
  require_command openssl

  primary_host="$(external_url_host)"
  primary_cert_pair="$(certificate_pair_for_host "$primary_host")"
  primary_cert="${primary_cert_pair%%|*}"
  primary_key="${primary_cert_pair#*|}"
  tmp="$(mktemp)"

  {
    cat <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $primary_host $DOMAIN_REDIRECT_HOSTS;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$primary_host\$request_uri;
    }
}

EOF

    for redirect_host in $DOMAIN_REDIRECT_HOSTS; do
      if [[ "$redirect_host" == "$primary_host" ]]; then
        continue
      fi
      redirect_cert_pair="$(certificate_pair_for_host "$redirect_host")"
      redirect_cert="${redirect_cert_pair%%|*}"
      redirect_key="${redirect_cert_pair#*|}"
      cat <<EOF
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $redirect_host;

    ssl_certificate $redirect_cert;
    ssl_certificate_key $redirect_key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    return 301 https://$primary_host\$request_uri;
}

EOF
    done

    cat <<EOF
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $primary_host;

    ssl_certificate $primary_cert;
    ssl_certificate_key $primary_key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    client_max_body_size 50m;

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types
        text/plain
        text/css
        application/json
        application/javascript
        application/xml
        image/svg+xml;

    location /_next/static/ {
        alias $CURRENT_LINK/frontend/.next/static/;
        expires 1y;
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        try_files \$uri =404;
    }

    location = /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /health/ {
        proxy_pass http://127.0.0.1:8000/health/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api/v1/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
  } > "$tmp"

  log "Installing nginx site for $primary_host"
  sudo install -m 0644 "$tmp" "$site_path"
  rm -f "$tmp"
  sudo ln -sfn "$site_path" "$enabled_path"
  sudo nginx -t
  sudo systemctl reload nginx || sudo systemctl restart nginx
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

wait_for_primary_external_url() {
  local url="$1"
  local max_attempts="${2:-15}"
  local attempt
  local response
  local http_code
  local redirect_url

  for attempt in $(seq 1 "$max_attempts"); do
    response="$(curl -k -sS -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 10 "$url" || true)"
    http_code="${response%% *}"
    redirect_url="${response#* }"
    if [[ "$http_code" =~ ^2[0-9][0-9]$ && -z "$redirect_url" ]]; then
      log "external primary domain is healthy"
      return 0
    fi
    log "external primary domain not ready: status=$http_code redirect=$redirect_url"
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
  wait_for_primary_external_url "$EXTERNAL_URL" 15 || status=1
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
  install_nginx_site
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
  prune_deploy_workspace

  if [[ "$ROLLBACK" -eq 1 ]]; then
    rollback_to_previous
    return
  fi

  bootstrap_shared_env
  sync_public_domain_env
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

  install_nginx_site
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
