#!/bin/bash
# Patroni вызывает скрипт один раз — после initdb на первом лидере.
# $1 — строка подключения суперпользователя. Пароли — из окружения контейнера.
set -euo pipefail

psql -v ON_ERROR_STOP=1 "$1" <<SQL
CREATE ROLE wordpress LOGIN PASSWORD '${WP_DB_PASSWORD}';
CREATE DATABASE wordpress OWNER wordpress ENCODING 'UTF8' TEMPLATE template0;
CREATE ROLE postgres_exporter LOGIN PASSWORD '${PG_EXPORTER_PASSWORD}' CONNECTION LIMIT 5;
GRANT pg_monitor TO postgres_exporter;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SQL
