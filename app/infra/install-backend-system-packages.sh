#!/bin/sh
# Install the digest-locked system packages of the backend images (unixODBC and the Microsoft ODBC
# Driver 18 for SQL Server, sql-review/PRDs/002-sql-server-connection Decision 4) and add the
# organization root CA to the system trust store (sql-review/PRDs/006-llm-connection Requirement 5).
#
# Usage: install-backend-system-packages.sh <connected|offline> <docker-arch> <lock-dir> \
#          <offline-package-dir> <ca-certificate>
# connected downloads every package from its admitted source; offline takes the same file names
# from <offline-package-dir>. Both verify the SHA-256 digest of the lock before installing, and
# apk itself never touches the network.
set -eu

mode="$1"
docker_arch="$2"
lock_dir="$3"
offline_dir="$4"
ca_certificate="$5"

alpine_source="https://dl-cdn.alpinelinux.org/alpine/v3.23/main"
microsoft_source="https://download.microsoft.com/download/0b3d5518-b4a7-4a2b-afc7-7ee9e967f93c"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

case "$docker_arch" in
    amd64|arm64) ;;
    *) echo "unsupported target architecture: $docker_arch" >&2; exit 64 ;;
esac
case "$mode" in
    connected|offline) ;;
    *) echo "DEPENDENCY_MODE must be connected or offline" >&2; exit 64 ;;
esac

# fetch <lock-file> <kind>: appends the verified local file of every record for this architecture
# to $work/<kind>.list.
fetch() {
    lock="$1"
    kind="$2"
    found=0
    : > "$work/$kind.list"
    while read -r record_arch alpine_arch package_spec expected_sha256; do
        case "$record_arch" in ""|\#*) continue ;; esac
        [ "$record_arch" = "$docker_arch" ] || continue
        if [ "$alpine_arch" != "$(apk --print-arch)" ]; then
            echo "lock architecture $alpine_arch does not match the image" >&2
            exit 65
        fi
        name="${package_spec%%=*}"
        version="${package_spec#*=}"
        if [ "$kind" = alpine ]; then
            file="${name}-${version}.apk"
            url="$alpine_source/$alpine_arch/$file"
        else
            file="${name}_${version}_${docker_arch}.apk"
            url="$microsoft_source/$file"
        fi
        if [ "$mode" = connected ]; then
            wget -q "$url" -O "$work/$file" || exit 66
        else
            cp "$offline_dir/$file" "$work/$file" || exit 66
        fi
        if ! echo "$expected_sha256  $work/$file" | sha256sum -c - >/dev/null; then
            echo "digest mismatch for $file" >&2
            exit 65
        fi
        echo "$work/$file" >> "$work/$kind.list"
        found=1
    done < "$lock"
    if [ "$found" -ne 1 ]; then
        echo "no locked package for $docker_arch in $lock" >&2
        exit 65
    fi
}

fetch "$lock_dir/backend-alpine-packages.lock" alpine
fetch "$lock_dir/msodbcsql18-alpine-packages.lock" microsoft
alpine_packages="$(cat "$work/alpine.list")"
microsoft_packages="$(cat "$work/microsoft.list")"

# Alpine packages keep apk's own signature check against the image's Alpine keys.
# shellcheck disable=SC2086
apk add --no-cache --no-network --repositories-file /dev/null $alpine_packages
# The Microsoft package carries no Alpine signature; its bytes are pinned by the lock digest,
# admitted after its detached OpenPGP signature verified against the Microsoft release key.
# ACCEPT_EULA records the owner's acceptance of the Microsoft EULA (PRD Decision 4); the Alpine
# package only prints the licence notice.
# shellcheck disable=SC2086
ACCEPT_EULA=Y apk add --no-cache --no-network --repositories-file /dev/null --allow-untrusted \
    $microsoft_packages </dev/null
odbcinst -q -d -n "ODBC Driver 18 for SQL Server" >/dev/null

install -m 0644 "$ca_certificate" /usr/local/share/ca-certificates/corporate-inference-root.crt
update-ca-certificates >/dev/null 2>&1
