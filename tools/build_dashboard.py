#!/usr/bin/env python3
"""Генератор дашборда «SRE / Platform Overview».

JSON дашборда собирается кодом, а не руками: так панели единообразны,
а изменения видны в диффе. Запуск:
    python3 tools/build_dashboard.py
Результат: config/grafana/dashboards/platform-overview.json
"""
import json
from pathlib import Path

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}

panels = []
_id = 0
_y = 0


def nid():
    global _id
    _id += 1
    return _id


def row(title):
    global _y
    panels.append({"type": "row", "title": title, "id": nid(), "collapsed": False,
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": _y}, "panels": []})
    _y += 1


def target(expr, legend="", ds=PROM, instant=False, ref="A"):
    t = {"datasource": ds, "expr": expr, "refId": ref, "legendFormat": legend}
    if instant:
        t["instant"] = True
        t["range"] = False
    return t


def panel(kind, title, targets, x, w, h=7, unit=None, desc="", thresholds=None,
          mappings=None, decimals=None, options=None, ds=PROM, min_=None, max_=None):
    defaults = {}
    if unit:
        defaults["unit"] = unit
    if decimals is not None:
        defaults["decimals"] = decimals
    if min_ is not None:
        defaults["min"] = min_
    if max_ is not None:
        defaults["max"] = max_
    if thresholds:
        defaults["thresholds"] = {"mode": "absolute", "steps": [
            {"color": c, "value": v} for v, c in thresholds]}
        defaults["color"] = {"mode": "thresholds"}
    if mappings:
        defaults["mappings"] = mappings
    p = {"type": kind, "title": title, "description": desc, "id": nid(), "datasource": ds,
         "gridPos": {"h": h, "w": w, "x": x, "y": _y},
         "targets": targets, "fieldConfig": {"defaults": defaults, "overrides": []},
         "options": options or {}}
    if kind == "timeseries":
        p["fieldConfig"]["defaults"].setdefault("custom", {"lineWidth": 1, "fillOpacity": 10, "showPoints": "never"})
        p["options"].setdefault("legend", {"displayMode": "list", "placement": "bottom"})
        p["options"].setdefault("tooltip", {"mode": "multi", "sort": "desc"})
    if kind == "stat":
        p["options"].setdefault("colorMode", "background")
        p["options"].setdefault("graphMode", "none")
        p["options"].setdefault("reduceOptions", {"calcs": ["lastNotNull"], "fields": "", "values": False})
    panels.append(p)
    return p


def next_line(h=7):
    global _y
    _y += h


RED_GREEN = [(None, "red"), (1, "green")]

# ============================================================ SLI
row("SLI — сайт глазами пользователя")
panel("stat", "Сайт доступен", [target('min(probe_success{job="blackbox_http"})', instant=True)],
      0, 4, h=5, thresholds=RED_GREEN,
      mappings=[{"type": "value", "options": {"0": {"text": "DOWN"}, "1": {"text": "UP"}}}],
      desc="Blackbox-проверка главной и /wp-login.php: HTTP 200 и в теле есть разметка WordPress.")
panel("stat", "Доступность за 24 ч (SLO 99.5%)",
      [target('avg_over_time(probe_success{job="blackbox_http", instance=~".*/"}[24h])', instant=True)],
      4, 5, h=5, unit="percentunit", decimals=3,
      thresholds=[(None, "red"), (0.99, "orange"), (0.995, "green")])
panel("stat", "Остаток бюджета ошибок (30 д)",
      [target('1 - (1 - avg_over_time(probe_success{job="blackbox_http", instance=~".*/"}[30d])) / 0.005', instant=True)],
      9, 5, h=5, unit="percentunit", decimals=1,
      thresholds=[(None, "red"), (0.25, "orange"), (0.5, "green")],
      desc="1 = бюджет не тронут, 0 = исчерпан. SLO 99.5% даёт ~3.6 ч простоя в месяц.")
panel("stat", "Доля 5xx (5 мин)",
      [target('(sum(rate({service="nginx"} | json status=\"status\" | __error__="" | status >= 500 [5m])) / sum(rate({service="nginx"} | json status=\"status\" | __error__="" [5m]))) or vector(0)',
              ds=LOKI, instant=True)],
      14, 5, h=5, unit="percentunit", decimals=2, ds=LOKI,
      thresholds=[(None, "green"), (0.01, "orange"), (0.05, "red")])
panels[-1]["fieldConfig"]["defaults"]["noValue"] = "0"
panel("stat", "Лидер PostgreSQL",
      [target('max by (instance) (patroni_primary == 1)', legend="{{instance}}", instant=True)],
      19, 5, h=5, thresholds=[(None, "blue")],
      options={"textMode": "name", "colorMode": "background", "graphMode": "none",
               "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})
next_line(5)

panel("timeseries", "Время ответа (blackbox)",
      [target('probe_duration_seconds{job="blackbox_http"}', "{{instance}}")], 0, 8, unit="s")
panel("timeseries", "Запросы в секунду (nginx)",
      [target('sum by (instance) (rate(nginx_http_requests_total[2m]))', "{{instance}}")], 8, 8, unit="reqps")
panel("timeseries", "Ответы по кодам (из логов)",
      [target('sum by (status) (rate({service="nginx"} | json status=\"status\" | __error__="" [2m]))', "{{status}}", ds=LOKI)],
      16, 8, unit="reqps", ds=LOKI)
next_line()

panel("timeseries", "Латентность p50/p95/p99 (request_time из логов)",
      [target('quantile_over_time(0.50, {service="nginx"} | json request_time=\"request_time\" | __error__="" | unwrap request_time [2m]) by (service)', "p50", ds=LOKI, ref="A"),
       target('quantile_over_time(0.95, {service="nginx"} | json request_time=\"request_time\" | __error__="" | unwrap request_time [2m]) by (service)', "p95", ds=LOKI, ref="B"),
       target('quantile_over_time(0.99, {service="nginx"} | json request_time=\"request_time\" | __error__="" | unwrap request_time [2m]) by (service)', "p99", ds=LOKI, ref="C")],
      0, 12, unit="s", ds=LOKI)
panel("timeseries", "Активные соединения nginx",
      [target('nginx_connections_active', "active {{instance}}", ref="A"),
       target('nginx_connections_waiting', "waiting {{instance}}", ref="B")], 12, 12)
next_line()

# ============================================================ App
row("Приложение — php-fpm и pgbouncer")
panel("timeseries", "php-fpm: процессы",
      [target('phpfpm_active_processes', "active", ref="A"),
       target('phpfpm_idle_processes', "idle", ref="B"),
       target('phpfpm_listen_queue', "в очереди", ref="C")], 0, 8,
      desc="Если active упирается в pm.max_children, а очередь растёт — нужны воркеры или оптимизация.")
panel("timeseries", "pgbouncer: клиентские соединения",
      [target('sum by (database) (pgbouncer_pools_client_active_connections)', "active {{database}}", ref="A"),
       target('sum by (database) (pgbouncer_pools_client_waiting_connections)', "waiting {{database}}", ref="B")],
      8, 8)
panel("timeseries", "pgbouncer: серверные соединения и ожидание",
      [target('sum by (database) (pgbouncer_pools_server_active_connections)', "server active {{database}}", ref="A"),
       target('sum by (database) (pgbouncer_pools_server_idle_connections)', "server idle {{database}}", ref="B"),
       target('max by (database) (pgbouncer_pools_client_maxwait_seconds)', "max wait, s {{database}}", ref="C")],
      16, 8)
next_line()

# ============================================================ DB
row("PostgreSQL / Patroni")
panel("table", "Роли узлов кластера",
      [target('max by (instance, scope) (patroni_primary)', instant=True, ref="A")],
      0, 6, h=7,
      mappings=[{"type": "value", "options": {"0": {"text": "replica", "color": "blue"},
                                              "1": {"text": "LEADER", "color": "green"}}}],
      options={"showHeader": True},
      desc="Источник — /metrics REST API Patroni.")
panels[-1]["transformations"] = [{"id": "organize", "options": {
    "excludeByName": {"Time": True}, "renameByName": {"Value": "role"}}}]
panels[-1]["fieldConfig"]["defaults"]["custom"] = {"cellOptions": {"type": "color-background"}}

panel("timeseries", "Отставание реплик (байты WAL)",
      [target('(max by (scope) (patroni_xlog_location) - on (scope) group_right patroni_xlog_replayed_location) '
              'and on (instance) (patroni_replica == 1)', "{{instance}}")],
      6, 6, unit="bytes",
      desc="Порог failover в кластере — 1 МБ (maximum_lag_on_failover).")
panel("timeseries", "Транзакции/с",
      [target('sum by (instance) (rate(pg_stat_database_xact_commit[2m]) + rate(pg_stat_database_xact_rollback[2m]))',
              "{{instance}}")], 12, 6, unit="ops")
panel("timeseries", "Соединения к PostgreSQL",
      [target('sum by (instance) (pg_stat_database_numbackends)', "{{instance}}", ref="A"),
       target('max(pg_settings_max_connections)', "max_connections", ref="B")], 18, 6)
next_line()

panel("timeseries", "Timeline (рост = был failover)",
      [target('max by (instance) (patroni_postgres_timeline)', "{{instance}}")], 0, 8, decimals=0)
panel("timeseries", "Cache hit ratio",
      [target('sum by (instance) (rate(pg_stat_database_blks_hit[5m])) / '
              '(sum by (instance) (rate(pg_stat_database_blks_hit[5m])) + sum by (instance) (rate(pg_stat_database_blks_read[5m])))',
              "{{instance}}")], 8, 8, unit="percentunit", min_=0, max_=1)
panel("timeseries", "Дедлоки и конфликты",
      [target('sum by (instance) (increase(pg_stat_database_deadlocks[5m]))', "deadlocks {{instance}}", ref="A"),
       target('sum by (instance) (increase(pg_stat_database_conflicts[5m]))', "conflicts {{instance}}", ref="B")],
      16, 8)
next_line()

# ============================================================ Consul
row("Consul — DCS для Patroni")
panel("stat", "Кластер здоров",
      [target('max(consul_autopilot_healthy)', instant=True)], 0, 4, h=5,
      thresholds=RED_GREEN,
      mappings=[{"type": "value", "options": {"0": {"text": "UNHEALTHY"}, "1": {"text": "OK"}}},
                {"type": "special", "options": {"match": "null", "result": {"text": "NO LEADER", "color": "red"}}}])
panel("stat", "Переживёт отказов серверов",
      [target('max(consul_autopilot_failure_tolerance)', instant=True)], 4, 4, h=5,
      thresholds=[(None, "red"), (1, "green")], decimals=0)
panel("stat", "Агенты Consul онлайн",
      [target('count(up{job="consul"} == 1)', instant=True), ], 8, 4, h=5, thresholds=[(None, "blue")])
panel("timeseries", "Raft: последний контакт с лидером",
      [target('max by (instance) (consul_raft_leader_lastContact{quantile="0.99"})', "{{instance}}")],
      12, 12, h=5, unit="ms")
next_line(5)

# ============================================================ Hosts
row("ВМ")
panel("timeseries", "CPU, %",
      [target('100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100', "{{instance}}")],
      0, 8, unit="percent", min_=0, max_=100)
panel("timeseries", "Память занята, %",
      [target('100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)', "{{instance}}")],
      8, 8, unit="percent", min_=0, max_=100)
panel("timeseries", "Диск занят, %",
      [target('max by (instance) (100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"} '
              '/ node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"}))', "{{instance}}")],
      16, 8, unit="percent", min_=0, max_=100,
      desc="Самая заполненная файловая система ВМ.")
next_line()

# ============================================================ Containers
row("Контейнеры (cAdvisor)")
panel("timeseries", "CPU по контейнерам",
      [target('sum by (name) (rate(container_cpu_usage_seconds_total{name=~"sre-.+"}[2m])) * 100', "{{name}}")],
      0, 12, unit="percent", desc="100% = одно ядро")
panel("timeseries", "Память по контейнерам",
      [target('max by (name) (container_memory_working_set_bytes{name=~"sre-.+"})', "{{name}}")],
      12, 12, unit="bytes")
next_line()

# ============================================================ Logs
row("Логи")
panel("logs", "Ошибки во всех логах",
      [target('{service=~".+"} |~ "(?i)(error|fatal|panic|critical)" != "level=info"', ds=LOKI)],
      0, 24, h=10, ds=LOKI,
      options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True})
next_line(10)

dashboard = {
    "uid": "sre-platform-overview",
    "title": "SRE / Platform Overview",
    "tags": ["sre", "wordpress", "patroni", "consul"],
    "timezone": "browser",
    "refresh": "30s",
    "time": {"from": "now-3h", "to": "now"},
    "schemaVersion": 39,
    "editable": False,
    "graphTooltip": 1,
    "links": [
        {"title": "Дашборды SRE", "type": "dashboards", "tags": ["sre"], "asDropdown": True, "keepTime": True},
        {"title": "Алерты", "type": "link", "url": "/alerting/groups", "targetBlank": False},
    ],
    "annotations": {"list": [
        {"name": "Смена лидера Patroni", "enable": True, "iconColor": "orange", "datasource": PROM,
         "expr": 'changes(max(patroni_postgres_timeline)[1m:15s]) > 0', "step": "30s",
         "titleFormat": "Failover / switchover"},
    ]},
    "panels": panels,
}

out = Path(__file__).resolve().parent.parent / "config/grafana/dashboards/platform-overview.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"{out} — {len(panels)} панелей")
