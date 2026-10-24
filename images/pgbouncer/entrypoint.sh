#!/bin/sh
set -eu
umask 077
# Пароли не зашиваем в образ: userlist создаётся из окружения при старте
cat > /etc/pgbouncer/userlist.txt <<EOF
"wordpress" "${WP_DB_PASSWORD}"
"pgbouncer_exporter" "${PGBOUNCER_STATS_PASSWORD}"
EOF
exec consul-template -config=/etc/consul-template/config.hcl
