# ==============================================================================
# PeeBot - PgBouncer Production Image
# ==============================================================================
# Extends the upstream PgBouncer image to bake in our config and entrypoint.
# This avoids bind mounts, which are unreliable in Coolify deployments
# (the cloned repo may not persist on the host at the expected path).
# ==============================================================================
FROM edoburu/pgbouncer:v1.24.1-p1

COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
COPY --chmod=0755 entrypoint.sh /usr/local/bin/pgbouncer-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/pgbouncer-entrypoint.sh"]
CMD ["/etc/pgbouncer/pgbouncer.ini"]
