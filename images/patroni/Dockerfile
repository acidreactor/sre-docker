# PostgreSQL 15 + Patroni на Ubuntu 22.04 (пакеты из официального репозитория PGDG)
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 TZ=Europe/Moscow

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg tzdata \
 && install -d /etc/apt/keyrings \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /etc/apt/keyrings/pgdg.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt jammy-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-common \
 # не создавать кластер main при установке — кластером управляет Patroni
 && sed -ri 's/^#?\s*create_main_cluster.*/create_main_cluster = false/' /etc/postgresql-common/createcluster.conf \
 && apt-get install -y --no-install-recommends postgresql-15 patroni python3-consul python3-psycopg2 \
 && rm -rf /var/lib/apt/lists/* \
 && install -d -o postgres -g postgres -m 0700 /var/lib/postgresql/data

COPY patroni.yml /etc/patroni.yml
COPY post_bootstrap.sh /usr/local/bin/post_bootstrap.sh
RUN chmod 0755 /usr/local/bin/post_bootstrap.sh && chown postgres:postgres /etc/patroni.yml

USER postgres
EXPOSE 5432 8008
CMD ["patroni", "/etc/patroni.yml"]
