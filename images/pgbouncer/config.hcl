consul {
  # Клиентский агент Consul стороны приложения
  address = "consul-app:8500"
  retry {
    enabled     = true
    attempts    = 0        # бесконечно
    backoff     = "250ms"
    max_backoff = "30s"
  }
}

log_level = "info"

wait {
  min = "2s"
  max = "10s"
}

template {
  source      = "/etc/consul-template/databases.ini.ctmpl"
  destination = "/etc/pgbouncer/databases.ini"
  perms       = 0640
}

# pgbouncer стартует только после первого рендера (когда лидер известен);
# при каждом новом рендере получает SIGHUP = перечитать конфиг
exec {
  command       = ["/usr/sbin/pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]
  reload_signal = "SIGHUP"
  kill_signal   = "SIGINT"
  kill_timeout  = "10s"
}
