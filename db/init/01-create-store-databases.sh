#!/bin/sh
# Runs once, on first container start. Creates one role + one database per store
# (plus a *_test database for automated tests). PUBLIC connect is revoked so a
# store role cannot open the other store's database.
set -eu

psql -v ON_ERROR_STOP=1 --username postgres \
  -v a_pw="$STORE_A_DB_PASSWORD" -v b_pw="$STORE_B_DB_PASSWORD" <<'SQL'
CREATE ROLE store_a_app LOGIN PASSWORD :'a_pw';
CREATE ROLE store_b_app LOGIN PASSWORD :'b_pw';

CREATE DATABASE store_a OWNER store_a_app;
CREATE DATABASE store_a_test OWNER store_a_app;
CREATE DATABASE store_b OWNER store_b_app;
CREATE DATABASE store_b_test OWNER store_b_app;

REVOKE CONNECT ON DATABASE store_a, store_a_test FROM PUBLIC;
REVOKE CONNECT ON DATABASE store_b, store_b_test FROM PUBLIC;
GRANT CONNECT ON DATABASE store_a, store_a_test TO store_a_app;
GRANT CONNECT ON DATABASE store_b, store_b_test TO store_b_app;
SQL
