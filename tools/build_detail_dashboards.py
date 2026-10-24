#!/usr/bin/env python3
"""Генератор детальных дашбордов Grafana (папка SRE).

    python3 tools/build_detail_dashboards.py

Создаёт в config/grafana/dashboards/:
  logs.json            — Логи: поток, подсчёт ошибок, nginx/PostgreSQL/PHP/pgbouncer, сами логи
  postgres.json        — PostgreSQL / Patroni детально
  web.json             — nginx, php-fpm, pgbouncer, blackbox
  consul.json          — Consul (DCS)
  host-containers.json — хост и контейнеры
Обзорный дашборд — tools/build_dashboard.py. Все дашборды связаны ссылками (тег sre).
"""
import json
from pathlib import Path

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
OUT = Path(__file__).resolve().parent.parent / "config/grafana/dashboards"

ERR_RE = '(?i)(error|fatal|panic|critical|exception|failed)'


class Dash:
    def __init__(self, uid, title, tags, variables=None, time_from="now-3h"):
        self.uid, self.title, self.tags = uid, title, tags
        self.variables = variables or []
        self.time_from = time_from
        self.panels, self._id, self.y = [], 0, 0

    def nid(self):
        self._id += 1
        return self._id

    def row(self, title):
        self.panels.append({"type": "row", "title": title, "id": self.nid(), "collapsed": False,
                            "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}, "panels": []})
        self.y += 1

    def next(self, h):
        self.y += h

    def panel(self, kind, title, targets, x, w, h=8, unit=None, desc="", thresholds=None,
              mappings=None, decimals=None, options=None, ds=PROM, min_=None, max_=None,
              stack=False, bars=False, overrides=None, transformations=None, custom=None, novalue=None):
        d = {}
        if novalue is not None: d["noValue"] = novalue
        if unit: d["unit"] = unit
        if decimals is not None: d["decimals"] = decimals
        if min_ is not None: d["min"] = min_
        if max_ is not None: d["max"] = max_
        if thresholds:
            d["thresholds"] = {"mode": "absolute",
                               "steps": [{"color": c, "value": v} for v, c in thresholds]}
            d["color"] = {"mode": "thresholds"}
        if mappings: d["mappings"] = mappings
        p = {"type": kind, "title": title, "description": desc, "id": self.nid(), "datasource": ds,
             "gridPos": {"h": h, "w": w, "x": x, "y": self.y}, "targets": targets,
             "fieldConfig": {"defaults": d, "overrides": overrides or []}, "options": options or {}}
        if kind == "timeseries":
            c = {"lineWidth": 1, "fillOpacity": 10, "showPoints": "never"}
            if stack:
                c["stacking"] = {"mode": "normal", "group": "A"}
                c["fillOpacity"] = 60
            if bars:
                c["drawStyle"] = "bars"
                c["fillOpacity"] = 80
            c.update(custom or {})
            d["custom"] = c
            p["options"].setdefault("legend", {"displayMode": "table", "placement": "right",
                                               "calcs": ["lastNotNull", "max"]})
            p["options"].setdefault("tooltip", {"mode": "multi", "sort": "desc"})
        if kind == "stat":
            p["options"].setdefault("colorMode", "background")
            p["options"].setdefault("graphMode", "area")
            p["options"].setdefault("reduceOptions", {"calcs": ["lastNotNull"], "fields": "", "values": False})
        if kind == "logs":
            p["options"] = {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending",
                            "enableLogDetails": True, "dedupStrategy": "none", "prettifyLogMessage": False}
        if kind == "bargauge":
            p["options"].setdefault("displayMode", "gradient")
            p["options"].setdefault("orientation", "horizontal")
            p["options"].setdefault("reduceOptions", {"calcs": ["lastNotNull"], "fields": "", "values": False})
        if transformations: p["transformations"] = transformations
        self.panels.append(p)
        return p

    def save(self, name):
        dash = {
            "uid": self.uid, "title": self.title, "tags": ["sre"] + self.tags,
            "timezone": "browser", "refresh": "30s", "schemaVersion": 39, "editable": False,
            "graphTooltip": 1, "time": {"from": self.time_from, "to": "now"},
            "templating": {"list": self.variables},
            "links": [{"title": "Дашборды SRE", "type": "dashboards", "tags": ["sre"],
                       "asDropdown": True, "includeVars": False, "keepTime": True}],
            "annotations": {"list": [
                {"name": "Смена лидера Patroni", "enable": True, "iconColor": "orange", "datasource": PROM,
                 "expr": "changes(max(patroni_postgres_timeline)[1m:15s]) > 0", "step": "30s",
                 "titleFormat": "Failover / switchover"}]},
            "panels": self.panels,
        }
        (OUT / name).write_text(json.dumps(dash, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{name}: {len(self.panels)} панелей")


def P(expr, legend="", ref="A", instant=False, zero=False):
    if zero:
        expr = f"({expr}) or vector(0)"
    t = {"datasource": PROM, "expr": expr, "refId": ref, "legendFormat": legend}
    if instant:
        t.update(instant=True, range=False, format="table")
    return t


def L(expr, legend="", ref="A", instant=False, zero=False):
    if zero:  # нет строк — нет рядов; подставляем 0, чтобы панель показывала 0, а не No data
        expr = f"({expr}) or vector(0)"
    t = {"datasource": LOKI, "expr": expr, "refId": ref, "legendFormat": legend, "queryType": "range"}
    if instant:
        t.update(queryType="instant", instant=True, range=False)
    return t


def prom_var(name, label, query, multi=True, all_=True):
    return {"type": "query", "name": name, "label": label, "datasource": PROM,
            "query": {"query": query, "refId": "PrometheusVariableQueryEditor-VariableQuery"},
            "definition": query, "refresh": 2, "sort": 1, "multi": multi, "includeAll": all_,
            "allValue": ".+", "current": {"text": "All", "value": "$__all"} if all_ else {}}


def loki_label_var(name, label, lbl):
    return {"type": "query", "name": name, "label": label, "datasource": LOKI,
            "query": {"type": 1, "label": lbl, "stream": "", "refId": "LokiVariableQueryEditor-VariableQuery"},
            "definition": f"label_values({lbl})", "refresh": 2, "sort": 1, "multi": True,
            "includeAll": True, "allValue": ".+", "current": {"text": "All", "value": "$__all"}}


def textbox(name, label):
    return {"type": "textbox", "name": name, "label": label, "query": "", "current": {"text": "", "value": ""}}


TABLE_NOTIME = [{"id": "organize", "options": {"excludeByName": {"Time": True}}}]
UPDOWN = [{"type": "value", "options": {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}]
RG = [(None, "red"), (1, "green")]


# ============================================================================ ЛОГИ
def logs():
    d = Dash("sre-logs", "SRE / Логи", ["logs", "loki"],
             [loki_label_var("service", "Сервис", "service"), textbox("search", "Поиск (regex)")],
             time_from="now-1h")
    S = '{service=~"$service"}'

    d.row("Общая картина")
    d.panel("stat", "Строк логов за период", [L(f'sum(count_over_time({S} |~ "$search" [$__range]))', instant=True, zero=True)],
            0, 4, 5, thresholds=[(None, "blue")], ds=LOKI, novalue="0", unit="short")
    d.panel("stat", "Ошибок за период", [L(f'sum(count_over_time({S} |~ "{ERR_RE}" [$__range]))', instant=True, zero=True)],
            4, 4, 5, thresholds=[(None, "green"), (1, "orange"), (100, "red")], ds=LOKI, novalue="0", unit="short",
            desc=f"Строки, где встречается {ERR_RE}")
    d.panel("stat", "Доля ошибок", [L(f'sum(count_over_time({S} |~ "{ERR_RE}" [$__range])) / sum(count_over_time({S} [$__range]))', instant=True, zero=True)],
            8, 4, 5, thresholds=[(None, "green"), (0.01, "orange"), (0.05, "red")], ds=LOKI, novalue="0", unit="percentunit", decimals=2)
    d.panel("stat", "5xx nginx за период",
            [L('sum(count_over_time({service="nginx"} | json status=\"status\" | __error__="" | status >= 500 [$__range]))', instant=True, zero=True)],
            12, 4, 5, thresholds=[(None, "green"), (1, "orange"), (50, "red")], ds=LOKI, novalue="0", unit="short")
    d.panel("stat", "FATAL/PANIC PostgreSQL",
            [L('sum(count_over_time({service=~"pg[0-9]", level=~"FATAL|PANIC"} [$__range]))', instant=True, zero=True)],
            16, 4, 5, thresholds=[(None, "green"), (1, "red")], ds=LOKI, novalue="0", unit="short")
    d.panel("stat", "PHP Fatal error",
            [L('sum(count_over_time({service="wordpress"} |= "PHP Fatal error" [$__range]))', instant=True, zero=True)],
            20, 4, 5, thresholds=[(None, "green"), (1, "red")], ds=LOKI, novalue="0", unit="short")
    d.next(5)

    d.panel("timeseries", "Поток логов по сервисам, строк",
            [L(f'sum by (service) (count_over_time({S} |~ "$search" [$__auto]))', "{{service}}")],
            0, 12, 8, ds=LOKI, stack=True, bars=True)
    d.panel("timeseries", "Ошибки по сервисам, строк",
            [L(f'sum by (service) (count_over_time({S} |~ "{ERR_RE}" [$__auto]))', "{{service}}")],
            12, 12, 8, ds=LOKI, novalue="0", stack=True, bars=True)
    d.next(8)

    d.panel("table", "Рейтинг сервисов по ошибкам за период",
            [L(f'sort_desc(sum by (service) (count_over_time({S} |~ "{ERR_RE}" [$__range])))', instant=True)],
            0, 8, 9, ds=LOKI,
            transformations=TABLE_NOTIME + [{"id": "organize", "options": {"renameByName": {"Value #A": "ошибок", "Value": "ошибок"}}}])
    d.panel("bargauge", "Объём логов по сервисам за период",
            [L(f'sort_desc(sum by (service) (count_over_time({S} [$__range])))', "{{service}}", instant=True)],
            8, 8, 9, ds=LOKI, unit="short")
    d.panel("timeseries", "Объём логов, байт/с",
            [L(f'sum by (service) (bytes_rate({S} [$__auto]))', "{{service}}")],
            16, 8, 9, ds=LOKI, unit="Bps", stack=True)
    d.next(9)

    d.row("nginx (access-лог в JSON)")
    d.panel("timeseries", "Ответы по кодам",
            [L('sum by (status) (count_over_time({service="nginx"} | json status=\"status\" | __error__="" [$__auto]))', "{{status}}")],
            0, 12, 8, ds=LOKI, stack=True, bars=True,
            overrides=[{"matcher": {"id": "byRegexp", "options": "5.."}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
                       {"matcher": {"id": "byRegexp", "options": "4.."}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]}])
    d.panel("timeseries", "Время ответа p50 / p95 / p99",
            [L(f'quantile_over_time({q}, {{service="nginx"}} | json request_time=\"request_time\" | __error__="" | unwrap request_time [$__auto]) by (service)', f"p{int(float(q)*100)}", ref=r)
             for q, r in (("0.5", "A"), ("0.95", "B"), ("0.99", "C"))],
            12, 12, 8, ds=LOKI, unit="s")
    d.next(8)
    d.panel("table", "Топ-10 URI по запросам",
            [L('topk(10, sum by (uri) (count_over_time({service="nginx"} | json uri=\"uri\" | __error__="" [$__range])))', instant=True)],
            0, 8, 9, ds=LOKI, transformations=TABLE_NOTIME)
    d.panel("table", "Топ URI с ошибками 4xx/5xx",
            [L('topk(10, sum by (uri, status) (count_over_time({service="nginx"} | json uri=\"uri\", status=\"status\" | __error__="" | status >= 400 [$__range])))', instant=True)],
            8, 8, 9, ds=LOKI, transformations=TABLE_NOTIME)
    d.panel("table", "Топ-10 клиентов (IP)",
            [L('topk(10, sum by (remote_addr) (count_over_time({service="nginx"} | json remote_addr=\"remote_addr\" | __error__="" [$__range])))', instant=True)],
            16, 8, 9, ds=LOKI, transformations=TABLE_NOTIME)
    d.next(9)
    d.panel("timeseries", "Самые медленные URI (max request_time)",
            [L('topk(5, max_over_time({service="nginx"} | json uri=\"uri\", request_time=\"request_time\" | __error__="" | unwrap request_time [$__auto]) by (uri))', "{{uri}}")],
            0, 12, 8, ds=LOKI, unit="s")
    d.panel("timeseries", "Отдано байт за интервал",
            [L('sum(sum_over_time({service="nginx"} | json bytes=\"bytes\" | __error__="" | unwrap bytes [$__auto]))', "отдано")],
            12, 12, 8, ds=LOKI, unit="bytes", bars=True)
    d.next(8)

    d.row("PostgreSQL / Patroni")
    d.panel("timeseries", "Сообщения по уровням",
            [L('sum by (level) (count_over_time({service=~"pg[0-9]", level=~"WARNING|ERROR|FATAL|PANIC"} [$__auto]))', "{{level}}")],
            0, 8, 8, ds=LOKI, novalue="0", stack=True, bars=True)
    d.panel("timeseries", "Медленные запросы (> 500 мс), длительность",
            [L('max_over_time({service=~"pg[0-9]"} |= "duration:" | regexp "duration: (?P<dur>[0-9.]+) ms" | unwrap dur [$__auto]) by (container)', "{{container}}")],
            8, 8, 8, ds=LOKI, novalue="0", unit="ms", desc="log_min_duration_statement = 500 мс")
    d.panel("timeseries", "События Patroni (лидер, промоут, демоут)",
            [L('sum by (service) (count_over_time({service=~"pg[0-9]"} |~ "(?i)(promoted|demot|acquired session lock|lock owner|following a different leader)" [$__auto]))', "{{service}}")],
            16, 8, 8, ds=LOKI, novalue="0", bars=True)
    d.next(8)
    d.panel("logs", "Ошибки PostgreSQL", [L('{service=~"pg[0-9]", level=~"ERROR|FATAL|PANIC|WARNING"}')], 0, 12, 10, ds=LOKI)
    d.panel("logs", "Patroni: смены ролей", [L('{service=~"pg[0-9]"} |~ "(?i)(promoted|demot|leader|following)" != "no action"')], 12, 12, 10, ds=LOKI)
    d.next(10)

    d.row("WordPress (PHP) и pgbouncer")
    d.panel("timeseries", "PHP: ошибки по типу",
            [L('sum by (php_level) (count_over_time({service="wordpress"} |~ "PHP (Fatal error|Warning|Notice|Deprecated|Parse error)" | regexp "PHP (?P<php_level>Fatal error|Warning|Notice|Deprecated|Parse error)" [$__auto]))', "{{php_level}}")],
            0, 12, 8, ds=LOKI, novalue="0", stack=True, bars=True)
    d.panel("timeseries", "pgbouncer: ошибки подключения к БД",
            [L('sum(count_over_time({service="pgbouncer"} |~ "(?i)(login failed|could not connect|server conn crashed|closing because)" [$__auto]))', "ошибки", zero=True)],
            12, 12, 8, ds=LOKI, bars=True, novalue="0")
    d.next(8)

    d.row("Уведомления Alertmanager (webhook)")
    d.panel("timeseries", "Уведомления по статусу",
            [L('sum by (status) (count_over_time({service="webhook-logger"} | json status="status" | __error__="" [$__auto]))', "{{status}}")],
            0, 8, 8, ds=LOKI, bars=True, novalue="0")
    d.panel("logs", "История уведомлений", [L('{service="webhook-logger"}')], 8, 16, 8, ds=LOKI)
    d.next(8)

    d.row("Сами логи")
    d.panel("logs", "Все логи (фильтр: сервис + поиск)", [L(f'{S} |~ "$search"')], 0, 24, 14, ds=LOKI)
    d.next(14)
    d.panel("logs", "Только ошибки", [L(f'{S} |~ "{ERR_RE}"')], 0, 24, 12, ds=LOKI)
    d.next(12)
    d.save("logs.json")


# ============================================================================ POSTGRESQL
def postgres():
    d = Dash("sre-postgres", "SRE / PostgreSQL и Patroni", ["postgres", "patroni"],
             [prom_var("instance", "Узел", "label_values(pg_up, instance)")])
    I = 'instance=~"$instance"'

    d.row("Кластер Patroni")
    d.panel("stat", "Лидер", [P('max by (instance) (patroni_primary == 1)', "{{instance}}")], 0, 4, 5,
            thresholds=[(None, "green")], options={"textMode": "name", "colorMode": "background", "graphMode": "none",
                                                   "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})
    d.panel("stat", "Реплик", [P('sum(patroni_replica)')], 4, 3, 5, thresholds=[(None, "red"), (1, "orange"), (2, "green")])
    d.panel("stat", "PostgreSQL запущен", [P(f'patroni_postgres_running{{{I}}}', "{{instance}}")], 7, 6, 5,
            thresholds=RG, mappings=UPDOWN, options={"colorMode": "background", "graphMode": "none", "textMode": "value_and_name",
                                                     "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})
    d.panel("stat", "Timeline", [P('max(patroni_postgres_timeline)')], 13, 3, 5, thresholds=[(None, "blue")], decimals=0,
            desc="Растёт на 1 при каждом failover/switchover")
    d.panel("stat", "Смен лидера за 24 ч", [P('changes(max(patroni_postgres_timeline)[24h:1m])')], 16, 4, 5,
            thresholds=[(None, "green"), (1, "orange"), (3, "red")], decimals=0)
    d.panel("stat", "Последний контакт с DCS", [P(f'time() - patroni_dcs_last_seen{{{I}}}', "{{instance}}")], 20, 4, 5,
            unit="s", thresholds=[(None, "green"), (20, "orange"), (30, "red")],
            options={"colorMode": "background", "graphMode": "none", "textMode": "value_and_name",
                     "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
            desc="Если > TTL (30 с) — узел потерял связь с Consul")
    d.next(5)
    d.panel("timeseries", "Роли узлов во времени (1 = лидер)", [P(f'patroni_primary{{{I}}}', "{{instance}}")], 0, 8, 7,
            min_=0, max_=1, custom={"lineInterpolation": "stepAfter", "lineWidth": 2})
    d.panel("timeseries", "Отставание реплик, байт WAL",
            [P('(max by (scope) (patroni_xlog_location) - on (scope) group_right patroni_xlog_replayed_location) and on (instance) (patroni_replica == 1)', "{{instance}}")],
            8, 8, 7, unit="bytes", desc="maximum_lag_on_failover = 1 МБ")
    d.panel("timeseries", "Отставание реплик, секунды", [P(f'pg_replication_lag_seconds{{{I}}}', "{{instance}}")], 16, 8, 7, unit="s")
    d.next(7)

    d.row("Нагрузка")
    d.panel("timeseries", "Транзакции/с (commit / rollback)",
            [P(f'sum by (instance) (rate(pg_stat_database_xact_commit{{{I}}}[2m]))', "commit {{instance}}", "A"),
             P(f'sum by (instance) (rate(pg_stat_database_xact_rollback{{{I}}}[2m]))', "rollback {{instance}}", "B")],
            0, 8, 8, unit="ops")
    d.panel("timeseries", "Строки/с: чтение и запись",
            [P(f'sum by (instance) (rate(pg_stat_database_tup_fetched{{{I}}}[2m]))', "fetched {{instance}}", "A"),
             P(f'sum by (instance) (rate(pg_stat_database_tup_inserted{{{I}}}[2m]))', "inserted {{instance}}", "B"),
             P(f'sum by (instance) (rate(pg_stat_database_tup_updated{{{I}}}[2m]))', "updated {{instance}}", "C"),
             P(f'sum by (instance) (rate(pg_stat_database_tup_deleted{{{I}}}[2m]))', "deleted {{instance}}", "D")],
            8, 8, 8, unit="rowsps")
    d.panel("timeseries", "Cache hit ratio",
            [P(f'sum by (instance) (rate(pg_stat_database_blks_hit{{{I}}}[5m])) / (sum by (instance) (rate(pg_stat_database_blks_hit{{{I}}}[5m])) + sum by (instance) (rate(pg_stat_database_blks_read{{{I}}}[5m])))', "{{instance}}")],
            16, 8, 8, unit="percentunit", min_=0, max_=1, desc="Норма для OLTP > 99%")
    d.next(8)

    d.row("Соединения и блокировки")
    d.panel("timeseries", "Соединения по состоянию",
            [P(f'sum by (instance, state) (pg_stat_activity_count{{{I}}})', "{{instance}} {{state}}")], 0, 8, 8, stack=True)
    d.panel("timeseries", "Соединения / max_connections",
            [P(f'sum by (instance) (pg_stat_database_numbackends{{{I}}}) / on (instance) max by (instance) (pg_settings_max_connections{{{I}}})', "{{instance}}")],
            8, 8, 8, unit="percentunit", min_=0, max_=1)
    d.panel("timeseries", "Самая долгая транзакция",
            [P(f'max by (instance, state) (pg_stat_activity_max_tx_duration{{{I}}})', "{{instance}} {{state}}")], 16, 8, 8, unit="s",
            desc="Долгие idle in transaction держат блокировки и мешают autovacuum")
    d.next(8)
    d.panel("timeseries", "Блокировки по типу", [P(f'sum by (mode) (pg_locks_count{{{I}}})', "{{mode}}")], 0, 8, 8, stack=True)
    d.panel("timeseries", "Дедлоки и конфликты",
            [P(f'sum by (instance) (increase(pg_stat_database_deadlocks{{{I}}}[5m]))', "deadlocks {{instance}}", "A"),
             P(f'sum by (instance) (increase(pg_stat_database_conflicts{{{I}}}[5m]))', "conflicts {{instance}}", "B")],
            8, 8, 8, bars=True)
    d.panel("timeseries", "Временные файлы, байт/с",
            [P(f'sum by (instance) (rate(pg_stat_database_temp_bytes{{{I}}}[5m]))', "{{instance}}")], 16, 8, 8, unit="Bps",
            desc="Сортировки не влезают в work_mem")
    d.next(8)

    d.row("Хранилище и запросы")
    d.panel("timeseries", "Размер баз", [P(f'pg_database_size_bytes{{{I}, datname!~"template.*"}}', "{{instance}} {{datname}}")], 0, 8, 8, unit="bytes")
    d.panel("timeseries", "Чекпойнты (по таймеру / по требованию)",
            [P(f'rate(pg_stat_bgwriter_checkpoints_timed_total{{{I}}}[10m]) * 600', "timed {{instance}}", "A"),
             P(f'rate(pg_stat_bgwriter_checkpoints_req_total{{{I}}}[10m]) * 600', "requested {{instance}}", "B")],
            8, 8, 8, desc="За 10 минут. Много requested — мал max_wal_size")
    d.panel("table", "Топ-10 запросов по суммарному времени (pg_stat_statements)",
            [P(f'topk(10, sum by (instance, queryid) (rate(pg_stat_statements_seconds_total{{{I}}}[10m])))', instant=True)],
            16, 8, 8, transformations=TABLE_NOTIME + [{"id": "organize", "options": {"renameByName": {"Value": "сек/с"}}}])
    d.next(8)
    d.save("postgres.json")


# ============================================================================ WEB
def web():
    d = Dash("sre-web", "SRE / Веб: nginx, php-fpm, pgbouncer", ["nginx", "php-fpm", "pgbouncer"])

    d.row("Внешние проверки (blackbox)")
    d.panel("stat", "Доступность", [P('probe_success{job="blackbox_http"}', "{{instance}}")], 0, 6, 5, thresholds=RG, mappings=UPDOWN,
            options={"colorMode": "background", "graphMode": "none", "textMode": "value_and_name",
                     "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})
    d.panel("stat", "HTTP-код", [P('probe_http_status_code{job="blackbox_http"}', "{{instance}}")], 6, 6, 5,
            thresholds=[(None, "red"), (200, "green"), (300, "orange")],
            options={"colorMode": "background", "graphMode": "none", "textMode": "value_and_name",
                     "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})
    d.panel("timeseries", "Время ответа по фазам",
            [P('sum by (phase) (probe_http_duration_seconds{job="blackbox_http", instance=~".*/"})', "{{phase}}")],
            12, 12, 9, unit="s", stack=True, desc="resolve / connect / processing / transfer — где теряется время")
    d.next(5)
    d.panel("timeseries", "Размер страницы", [P('probe_http_uncompressed_body_length{job="blackbox_http"}', "{{instance}}")],
            0, 12, 4, unit="bytes")
    d.next(4)

    d.row("nginx")
    d.panel("timeseries", "Запросы/с", [P('sum(rate(nginx_http_requests_total[2m]))', "RPS")], 0, 8, 8, unit="reqps")
    d.panel("timeseries", "Соединения по состоянию",
            [P('nginx_connections_reading', "reading", "A"), P('nginx_connections_writing', "writing", "B"),
             P('nginx_connections_waiting', "waiting (keep-alive)", "C")], 8, 8, 8, stack=True)
    d.panel("timeseries", "Принятые vs обработанные соединения",
            [P('rate(nginx_connections_accepted[2m])', "accepted", "A"), P('rate(nginx_connections_handled[2m])', "handled", "B")],
            16, 8, 8, unit="cps", desc="Разница = отброшенные соединения (лимит worker_connections)")
    d.next(8)

    d.row("php-fpm")
    d.panel("stat", "Воркеров активно / всего",
            [P('phpfpm_active_processes', "active", "A"), P('phpfpm_total_processes', "total", "B")], 0, 4, 8,
            thresholds=[(None, "blue")], options={"colorMode": "value", "graphMode": "area", "textMode": "value_and_name",
                                                  "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})
    d.panel("timeseries", "Процессы", [P('phpfpm_active_processes', "active", "A"), P('phpfpm_idle_processes', "idle", "B")],
            4, 7, 8, stack=True)
    d.panel("timeseries", "Очередь и упор в max_children",
            [P('phpfpm_listen_queue', "в очереди", "A"), P('increase(phpfpm_max_children_reached[5m])', "max_children reached", "B")],
            11, 7, 8)
    d.panel("timeseries", "Принято запросов/с и медленные",
            [P('rate(phpfpm_accepted_connections[2m])', "запросов/с", "A"), P('increase(phpfpm_slow_requests[5m])', "slow (> 5 с)", "B")],
            18, 6, 8)
    d.next(8)

    d.row("pgbouncer")
    d.panel("timeseries", "Клиенты: активные / ждут",
            [P('sum by (database) (pgbouncer_pools_client_active_connections{database!="pgbouncer"})', "active {{database}}", "A"),
             P('sum by (database) (pgbouncer_pools_client_waiting_connections{database!="pgbouncer"})', "waiting {{database}}", "B")],
            0, 8, 8)
    d.panel("timeseries", "Серверные соединения к PostgreSQL",
            [P('sum by (database) (pgbouncer_pools_server_active_connections{database!="pgbouncer"})', "active {{database}}", "A"),
             P('sum by (database) (pgbouncer_pools_server_idle_connections{database!="pgbouncer"})', "idle {{database}}", "B"),
             P('sum by (database) (pgbouncer_pools_server_used_connections{database!="pgbouncer"})', "used {{database}}", "C")],
            8, 8, 8, stack=True)
    d.panel("timeseries", "Максимальное ожидание клиента",
            [P('max by (database) (pgbouncer_pools_client_maxwait_seconds{database!="pgbouncer"})', "{{database}}")], 16, 8, 8, unit="s")
    d.next(8)
    d.panel("timeseries", "Запросы и транзакции/с",
            [P('sum by (database) (rate(pgbouncer_stats_queries_pooled_total{database!="pgbouncer"}[2m]))', "queries {{database}}", "A"),
             P('sum by (database) (rate(pgbouncer_stats_transactions_pooled_total{database!="pgbouncer"}[2m]))', "transactions {{database}}", "B")],
            0, 8, 8, unit="ops")
    d.panel("timeseries", "Среднее время запроса",
            [P('sum by (database) (rate(pgbouncer_stats_queries_duration_seconds_total{database!="pgbouncer"}[2m])) / sum by (database) (rate(pgbouncer_stats_queries_pooled_total{database!="pgbouncer"}[2m]))', "{{database}}")],
            8, 8, 8, unit="s")
    d.panel("timeseries", "Трафик через пул",
            [P('sum(rate(pgbouncer_stats_received_bytes_total[2m]))', "от клиентов", "A"),
             P('sum(rate(pgbouncer_stats_sent_bytes_total[2m]))', "клиентам", "B")], 16, 8, 8, unit="Bps")
    d.next(8)
    d.save("web.json")


# ============================================================================ CONSUL
def consul():
    d = Dash("sre-consul", "SRE / Consul", ["consul"])
    d.row("Кворум")
    d.panel("stat", "Кластер здоров", [P('max(consul_autopilot_healthy)')], 0, 4, 5, thresholds=RG,
            mappings=[{"type": "value", "options": {"0": {"text": "UNHEALTHY"}, "1": {"text": "OK"}}},
                      {"type": "special", "options": {"match": "null", "result": {"text": "NO LEADER", "color": "red"}}}])
    d.panel("stat", "Переживёт отказов серверов", [P('max(consul_autopilot_failure_tolerance)')], 4, 4, 5,
            thresholds=[(None, "red"), (1, "green")], decimals=0)
    d.panel("stat", "Агенты отвечают", [P('count(up{job="consul"} == 1)'), ], 8, 4, 5, thresholds=[(None, "red"), (4, "green")], decimals=0,
            desc="3 сервера + consul-app")
    d.panel("stat", "Сервисов в каталоге", [P('max(consul_state_services)')], 12, 4, 5, thresholds=[(None, "blue")], decimals=0)
    d.panel("stat", "Узлов в каталоге", [P('max(consul_state_nodes)')], 16, 4, 5, thresholds=[(None, "blue")], decimals=0)
    d.panel("stat", "Доступность агентов", [P('up{job="consul"}', "{{instance}}")], 20, 4, 5, thresholds=RG, mappings=UPDOWN,
            options={"colorMode": "background", "graphMode": "none", "textMode": "value_and_name",
                     "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})
    d.next(5)
    d.row("Raft")
    d.panel("timeseries", "Последний контакт с лидером (p99)",
            [P('max by (instance) (consul_raft_leader_lastContact{quantile="0.99"})', "{{instance}}")], 0, 8, 8, unit="ms",
            desc="Растёт — сеть/диск тормозят, близко к выборам нового лидера")
    d.panel("timeseries", "Время коммита Raft (p99)",
            [P('max by (instance) (consul_raft_commitTime{quantile="0.99"})', "{{instance}}")], 8, 8, 8, unit="ms")
    d.panel("timeseries", "Применений в Raft/с",
            [P('sum by (instance) (rate(consul_raft_apply[2m]))', "{{instance}}")], 16, 8, 8, unit="ops",
            desc="Записи в KV: Patroni продлевает блокировку лидера каждые loop_wait")
    d.next(8)
    d.row("Нагрузка на агенты")
    d.panel("timeseries", "RPC-запросы/с", [P('sum by (instance) (rate(consul_rpc_request[2m]))', "{{instance}}")], 0, 12, 8, unit="reqps")
    d.panel("timeseries", "Операции KV/с", [P('sum by (instance) (rate(consul_kvs_apply_count[2m]))', "{{instance}}")], 12, 12, 8, unit="ops")
    d.next(8)
    d.save("consul.json")


# ============================================================================ HOST + CONTAINERS
def host():
    d = Dash("sre-host", "SRE / Хост и контейнеры", ["host", "docker"],
             [prom_var("container", "Контейнер", 'label_values(container_memory_working_set_bytes{name=~"sre-.+"}, name)')])
    C = 'name=~"$container"'
    d.row("Хост")
    d.panel("stat", "Uptime", [P('time() - node_boot_time_seconds')], 0, 4, 5, unit="s", thresholds=[(None, "blue")])
    d.panel("stat", "CPU ядер", [P('count(node_cpu_seconds_total{mode="idle"})')], 4, 4, 5, thresholds=[(None, "blue")])
    d.panel("stat", "RAM", [P('node_memory_MemTotal_bytes')], 8, 4, 5, unit="bytes", thresholds=[(None, "blue")])
    d.panel("stat", "Load average (5m) / ядро", [P('node_load5 / scalar(count(node_cpu_seconds_total{mode="idle"}))')], 12, 4, 5,
            decimals=2, thresholds=[(None, "green"), (0.8, "orange"), (1.2, "red")])
    d.panel("stat", "Память занята", [P('1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes')], 16, 4, 5,
            unit="percentunit", thresholds=[(None, "green"), (0.8, "orange"), (0.9, "red")])
    d.panel("stat", "Контейнеров", [P('count(container_last_seen{name=~"sre-.+"})')], 20, 4, 5, thresholds=[(None, "blue")])
    d.next(5)
    d.panel("timeseries", "CPU по режимам",
            [P('sum by (mode) (rate(node_cpu_seconds_total{mode!="idle"}[2m])) / scalar(count(node_cpu_seconds_total{mode="idle"}))', "{{mode}}")],
            0, 8, 8, unit="percentunit", stack=True, max_=1)
    d.panel("timeseries", "Память",
            [P('node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes', "занято", "A"),
             P('node_memory_Cached_bytes + node_memory_Buffers_bytes', "кэш", "B"),
             P('node_memory_MemTotal_bytes', "всего", "C")], 8, 8, 8, unit="bytes")
    d.panel("timeseries", "Диск: заполненность ФС",
            [P('100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"})', "{{mountpoint}}")],
            16, 8, 8, unit="percent", min_=0, max_=100)
    d.next(8)
    d.panel("timeseries", "Диск: IO, байт/с",
            [P('sum by (device) (rate(node_disk_read_bytes_total[2m]))', "read {{device}}", "A"),
             P('sum by (device) (rate(node_disk_written_bytes_total[2m]))', "write {{device}}", "B")], 0, 8, 8, unit="Bps")
    d.panel("timeseries", "Диск: загрузка (util)",
            [P('rate(node_disk_io_time_seconds_total[2m])', "{{device}}")], 8, 8, 8, unit="percentunit", max_=1)
    d.panel("timeseries", "Сеть, байт/с",
            [P('sum by (device) (rate(node_network_receive_bytes_total{device!~"lo|veth.*|br-.*|docker.*"}[2m]))', "rx {{device}}", "A"),
             P('sum by (device) (rate(node_network_transmit_bytes_total{device!~"lo|veth.*|br-.*|docker.*"}[2m]))', "tx {{device}}", "B")],
            16, 8, 8, unit="Bps")
    d.next(8)

    d.row("Контейнеры (cAdvisor)")
    d.panel("timeseries", "CPU по контейнерам (100% = 1 ядро)",
            [P(f'sum by (name) (rate(container_cpu_usage_seconds_total{{{C}}}[2m])) * 100', "{{name}}")], 0, 12, 9, unit="percent")
    d.panel("timeseries", "Память по контейнерам",
            [P(f'max by (name) (container_memory_working_set_bytes{{{C}}})', "{{name}}")], 12, 12, 9, unit="bytes")
    d.next(9)
    d.panel("bargauge", "Топ-10 по памяти сейчас",
            [P(f'topk(10, max by (name) (container_memory_working_set_bytes{{{C}}}))', "{{name}}")], 0, 8, 9, unit="bytes")
    d.panel("timeseries", "Сеть контейнеров: приём",
            [P(f'sum by (name) (rate(container_network_receive_bytes_total{{{C}, interface="eth0"}}[2m]))', "{{name}}")], 8, 8, 9, unit="Bps")
    d.panel("timeseries", "Сеть контейнеров: передача",
            [P(f'sum by (name) (rate(container_network_transmit_bytes_total{{{C}, interface="eth0"}}[2m]))', "{{name}}")], 16, 8, 9, unit="Bps")
    d.next(9)

    d.row("Цели Prometheus")
    d.panel("table", "Состояние всех целей", [P('up', instant=True)], 0, 24, 10,
            mappings=UPDOWN,
            transformations=[{"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True},
                                                             "renameByName": {"Value": "up"}}}],
            options={"showHeader": True})
    d.panels[-1]["fieldConfig"]["overrides"] = [
        {"matcher": {"id": "byName", "options": "up"},
         "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background"}},
                        {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}}]}]
    d.next(10)
    d.save("host-containers.json")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    logs(); postgres(); web(); consul(); host()
