# Sourced by the scripts that reach the local Compose stack; running it alone does nothing.
#
# The Compose project name keeps the containers, networks, volumes and images of this checkout apart
# from another checkout of the same project on this machine. COMPOSE_PROJECT_NAME in the shell
# environment, else in the Git-ignored app/infra/.env, replaces the product short name. The name may
# hold only lowercase letters, digits and hyphens, and starts and ends with a letter or digit.
compose_project_name() {
  compose_project="${COMPOSE_PROJECT_NAME:-}"
  if [ -z "$compose_project" ] && [ -f "$1/app/infra/.env" ]; then
    compose_project="$(
      sed -n -E 's/^[[:space:]]*(export[[:space:]]+)?COMPOSE_PROJECT_NAME=//p' "$1/app/infra/.env" |
        tail -n 1 |
        tr -d '\r' |
        sed -E 's/[[:space:]]+$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
    )"
  fi
  compose_project="${compose_project:-dwhcodereview}"
  case "$compose_project" in
    *[!a-z0-9-]* | -* | *-)
      echo "Compose proje adı geçersiz: COMPOSE_PROJECT_NAME yalnız küçük harf, rakam ve kısa çizgi içerebilir; kısa çizgiyle başlayamaz ve bitemez (örnek: ikinci-kopya)." >&2
      return 1
      ;;
  esac
  printf '%s\n' "$compose_project"
}
