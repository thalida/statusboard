#!/bin/sh
# What the page reads at start, written from the environment.
#
# A Vite build inlines a VITE_ value, which would make this image
# environment-specific. The same image then could not be the one CI
# proved. api/entrypoint.sh picks a process the same way.
set -eu

: "${API_URL:?API_URL is unset, so the client would call nothing}"

cat > /usr/share/nginx/html/config.js <<EOF
window.STATUSBOARD_CONFIG = { apiUrl: "${API_URL}" };
EOF

# The image's own entrypoint renders the nginx template, then runs
# the command. Skipping it would leave the template unrendered.
exec /docker-entrypoint.sh "$@"
