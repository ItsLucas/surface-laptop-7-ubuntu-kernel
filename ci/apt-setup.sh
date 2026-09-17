#!/usr/bin/env bash
set -euo pipefail
# Only run in a disposable Ubuntu container, never on the laptop.
test -f /.dockerenv
source /etc/os-release
test "$VERSION_ID" = 26.10
test "$VERSION_CODENAME" = stonking
test "$(dpkg --print-architecture)" = arm64
cat > /etc/apt/sources.list.d/ubuntu.sources <<'EOF'
Types: deb deb-src
URIs: http://ports.ubuntu.com/ubuntu-ports
Suites: stonking stonking-updates stonking-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates python3 python3-apt git
