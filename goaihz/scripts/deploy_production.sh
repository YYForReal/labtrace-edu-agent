#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
remote_host="${LABTRACE_DEPLOY_HOST:-root@111.228.14.43}"
remote_base="${LABTRACE_REMOTE_BASE:-/opt/labtrace}"
remote_compose="${LABTRACE_REMOTE_COMPOSE:-/opt/labtrace-current/goaihz/docker-compose.production.yml}"
model_env_source="${LABTRACE_MODEL_ENV_FILE:-$repo_root/.env}"
sync_model_env="${LABTRACE_SYNC_MODEL_ENV:-true}"
expected_branch="${LABTRACE_DEPLOY_BRANCH:-main}"
ssh_control_path="${LABTRACE_SSH_CONTROL_PATH:-}"
ssh_cmd=(ssh)
scp_cmd=(scp -q)
rsync_ssh="ssh"
if [[ -n "$ssh_control_path" ]]; then
  ssh_cmd+=(-o "ControlPath=$ssh_control_path")
  scp_cmd+=(-o "ControlPath=$ssh_control_path")
  rsync_ssh+=" -o ControlPath=$ssh_control_path"
fi

cd "$repo_root"

branch="$(git branch --show-current)"
if [[ "$branch" != "$expected_branch" ]]; then
  echo "Refusing to deploy branch '$branch'; expected '$expected_branch'." >&2
  exit 1
fi

commit="$(git rev-parse HEAD)"
short_commit="$(git rev-parse --short=12 HEAD)"
release_dir="${remote_base}.release-${short_commit}"
image="labtrace-edu-agent:${short_commit}"

if ! git ls-remote --exit-code --heads origin "$expected_branch" >/dev/null 2>&1; then
  echo "origin/$expected_branch does not exist. Push the branch before deployment." >&2
  exit 1
fi

remote_commit="$(git ls-remote origin "refs/heads/$expected_branch" | awk '{print $1}')"
if [[ "$remote_commit" != "$commit" ]]; then
  echo "Local HEAD is not the commit currently published at origin/$expected_branch." >&2
  exit 1
fi

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/labtrace-release.XXXXXX")"
cleanup() {
  rm -rf "$work_dir"
}
trap cleanup EXIT

git archive "$commit" | tar -x -C "$work_dir"
if [[ ! -d "$repo_root/frontend/node_modules" ]]; then
  echo "frontend/node_modules is missing; run npm install before deployment." >&2
  exit 1
fi

# Build from the immutable archived commit, not from unrelated dirty files in
# the working tree. The dependency directory is only linked for the build and
# is removed before the release is transferred.
ln -s "$repo_root/frontend/node_modules" "$work_dir/frontend/node_modules"
env VITE_PUBLIC_BASE=/education/ npm --prefix "$work_dir/frontend" run build
rm "$work_dir/frontend/node_modules"

if [[ "$sync_model_env" == "true" ]]; then
  if [[ ! -f "$model_env_source" ]]; then
    echo "Model environment file is missing: $model_env_source" >&2
    exit 1
  fi
  model_env_temp="$work_dir/labtrace.env"
  umask 077
  : >"$model_env_temp"
  required_model_keys=(LLM_PROVIDER LLM_BASE_URL LLM_API_KEY LLM_MODEL)
  for model_key in "${required_model_keys[@]}"; do
    model_value="$(
      awk -v target="$model_key" '
        index($0, target "=") == 1 {
          print substr($0, length(target) + 2)
          exit
        }
      ' "$model_env_source"
    )"
    model_value="${model_value%$'\r'}"
    if [[ -z "$model_value" ]]; then
      echo "Required model variable is empty: $model_key" >&2
      exit 1
    fi
    printf '%s=%s\n' "$model_key" "$model_value" >>"$model_env_temp"
  done
  remote_model_temp="/tmp/labtrace-model-${short_commit}.env"
  "${scp_cmd[@]}" "$model_env_temp" "$remote_host:$remote_model_temp"
  "${ssh_cmd[@]}" "$remote_host" \
    "set -e
     install -d -m 700 /etc/labtrace
     install -m 600 '$remote_model_temp' /etc/labtrace/labtrace.env
     rm -f '$remote_model_temp'"
else
  "${ssh_cmd[@]}" "$remote_host" "test -s /etc/labtrace/labtrace.env"
fi

"${ssh_cmd[@]}" "$remote_host" "mkdir -p '$release_dir'"
rsync -az --delete -e "$rsync_ssh" \
  --exclude '.git' \
  --exclude 'goaihz/submission' \
  --exclude 'goaihz/tmp' \
  --exclude 'goaihz/*.zip' \
  "$work_dir/" "$remote_host:$release_dir/"

"${ssh_cmd[@]}" "$remote_host" \
  "set -e
   install -d -o 10001 -g 10001 /var/lib/labtrace/demo_tasks
   cd '$release_dir'
   docker build -f goaihz/Dockerfile.production -t '$image' .
   ln -sfn '$release_dir' /opt/labtrace-current
   LABTRACE_IMAGE='$image' docker compose -f '$remote_compose' up -d --remove-orphans
   for attempt in \$(seq 1 30); do
     if curl -fsS http://172.17.0.1:8792/health >/dev/null; then
       exit 0
     fi
     sleep 2
   done
   docker logs --tail 100 labtrace-goaihz
   exit 1"

echo "Deployed commit $commit as image $image."
echo "Application health: http://172.17.0.1:8792/health"
