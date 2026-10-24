# pgbouncer под управлением consul-template (Ubuntu 22.04).
# consul-template в режиме exec: ждёт адрес лидера в Consul, рендерит databases.ini,
# запускает pgbouncer дочерним процессом и при смене лидера шлёт ему SIGHUP (reload).
FROM hashicorp/consul-template:0.40.0 AS ct

FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive TZ=Europe/Moscow
RUN apt-get update \
 && apt-get install -y --no-install-recommends pgbouncer ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ct /bin/consul-template /usr/local/bin/consul-template
COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
COPY config.hcl databases.ini.ctmpl /etc/consul-template/
COPY entrypoint.sh /entrypoint.sh

RUN chmod 0755 /entrypoint.sh \
 && install -d -o postgres -g postgres /var/run/postgresql \
 && chown -R postgres:postgres /etc/pgbouncer

# pgbouncer отказывается работать от root
USER postgres
EXPOSE 5432
ENTRYPOINT ["/entrypoint.sh"]
