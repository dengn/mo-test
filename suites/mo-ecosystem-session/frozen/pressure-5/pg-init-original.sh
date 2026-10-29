#!/bin/sh
set -eu
apk add --no-cache postgresql16 postgresql16-contrib
mkdir -p /var/lib/postgresql/data /run/postgresql
chown -R postgres:postgres /var/lib/postgresql /run/postgresql
printf '%s\n' 'compat4-local' > /tmp/eco4-pg-password
chown postgres:postgres /tmp/eco4-pg-password
chmod 600 /tmp/eco4-pg-password
su postgres -c 'initdb -D /var/lib/postgresql/data --username=postgres --pwfile=/tmp/eco4-pg-password --auth-host=scram-sha-256 --auth-local=trust'
printf '\nhost all all 0.0.0.0/0 scram-sha-256\nhost replication all 0.0.0.0/0 scram-sha-256\n' >> /var/lib/postgresql/data/pg_hba.conf
exec su postgres -c 'exec postgres -D /var/lib/postgresql/data -c listen_addresses=* -c wal_level=logical -c max_replication_slots=10 -c max_wal_senders=10'
