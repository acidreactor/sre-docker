# WordPress 6.5 (php-fpm 8.1) + расширение pgsql + PG4WP — слой совместимости с PostgreSQL.
# Версия WordPress зафиксирована: PG4WP v3 протестирован на WP 6.4–6.5.
FROM wordpress:6.5.5-php8.1-fpm

RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq-dev unzip \
 && docker-php-ext-install pgsql \
 && rm -rf /var/lib/apt/lists/*

# Официальный entrypoint копирует /usr/src/wordpress в том /var/www/html при первом старте,
# поэтому PG4WP кладём в исходник — он попадёт на сайт вместе с WordPress.
# Источник: локальный pg4wp.zip рядом с Dockerfile (если GitHub недоступен) или GitHub.
COPY . /tmp/src/
RUN set -eux; \
    if [ -f /tmp/src/pg4wp.zip ]; then \
      cp /tmp/src/pg4wp.zip /tmp/pg4wp.zip; \
    else \
      curl -fSL --retry 3 --connect-timeout 20 -o /tmp/pg4wp.zip \
        https://github.com/PostgreSQL-For-Wordpress/postgresql-for-wordpress/archive/refs/heads/v3.zip; \
    fi; \
    unzip -q /tmp/pg4wp.zip -d /tmp/pg4wp; \
    # db.php лежит либо в каталоге pg4wp/, либо в корне архива — берём каталог, где он есть
    DBPHP="$(find /tmp/pg4wp -type f -name db.php | head -1)"; \
    test -n "$DBPHP"; \
    cp -r "$(dirname "$DBPHP")" /usr/src/wordpress/wp-content/pg4wp; \
    cp /usr/src/wordpress/wp-content/pg4wp/db.php /usr/src/wordpress/wp-content/db.php; \
    if grep -q "DB_DRIVER" /usr/src/wordpress/wp-content/db.php; then \
      sed -ri "s/define\(\s*'DB_DRIVER'.*/define('DB_DRIVER', 'pgsql');/" /usr/src/wordpress/wp-content/db.php; \
    else \
      sed -i "1a define('DB_DRIVER', 'pgsql');" /usr/src/wordpress/wp-content/db.php; \
    fi; \
    grep -n "DB_DRIVER" /usr/src/wordpress/wp-content/db.php; \
    ls /usr/src/wordpress/wp-content/pg4wp; \
    chown -R www-data:www-data /usr/src/wordpress/wp-content; \
    rm -rf /tmp/pg4wp /tmp/pg4wp.zip /tmp/src

COPY zzz-sre.conf /usr/local/etc/php-fpm.d/zzz-sre.conf
COPY sre.ini /usr/local/etc/php/conf.d/zz-sre.ini
