#!/bin/bash
# 把本地导出的数据导入 TiDB Cloud，并建只读账号、生成 .env.cloud
# 用法（在 chatbi 文件夹里）：bash deploy/import_to_tidb.sh
set -euo pipefail
cd "$(dirname "$0")"

source ../.env.tidb   # TIDB_HOST / TIDB_PORT / TIDB_USER / TIDB_PASSWORD / TIDB_RO_PASSWORD

# 密码写进一个只有自己能读的临时配置文件，不出现在命令行里（ps 看不到），用完即删
CNF=$(mktemp)
chmod 600 "$CNF"
trap 'rm -f "$CNF"' EXIT
printf '[client]\npassword=%s\n' "$TIDB_PASSWORD" > "$CNF"

tidb() {
  /usr/local/mysql/bin/mysql --defaults-extra-file="$CNF" \
    -h "$TIDB_HOST" -P "$TIDB_PORT" -u "$TIDB_USER" \
    --ssl-mode=VERIFY_IDENTITY --ssl-ca=/etc/ssl/cert.pem \
    --local-infile=1 --default-character-set=utf8mb4 "$@"
}

echo "① 建库建表"
tidb < schema.sql

echo "② 导入 ub（20 个分片，每片 50 万行）"
for f in export/ub_part_*; do
  tidb taobao -e "LOAD DATA LOCAL INFILE '$f' INTO TABLE ub FIELDS TERMINATED BY '\t' LINES TERMINATED BY '\n'"
  echo "   $f 完成"
done

echo "③ 导入 user_rfm"
tidb taobao -e "LOAD DATA LOCAL INFILE 'export/user_rfm.tsv' INTO TABLE user_rfm FIELDS TERMINATED BY '\t' LINES TERMINATED BY '\n'"

echo "④ 建索引（可能要几分钟）"
tidb < indexes.sql

echo "⑤ 建只读账号（TiDB Starter 的用户名必须带前缀，和 root 的前缀相同）"
PREFIX="${TIDB_USER%%.*}"
RO_USER="${PREFIX}.chatbi_ro"
tidb -e "CREATE USER IF NOT EXISTS '${RO_USER}'@'%' IDENTIFIED BY '${TIDB_RO_PASSWORD}';
         GRANT SELECT ON taobao.ub TO '${RO_USER}'@'%';
         GRANT SELECT ON taobao.user_rfm TO '${RO_USER}'@'%';"

echo "⑥ 核对行数（应为 9980301 和 67421）"
tidb taobao -e "SELECT COUNT(*) AS ub_rows FROM ub; SELECT COUNT(*) AS rfm_rows FROM user_rfm;"

echo "⑦ 生成 .env.cloud（DeepSeek 配置沿用 .env，数据库换成 TiDB 只读账号）"
grep -v '^MYSQL_' ../.env > ../.env.cloud
cat >> ../.env.cloud <<EOF
MYSQL_HOST=${TIDB_HOST}
MYSQL_PORT=${TIDB_PORT}
MYSQL_USER=${RO_USER}
MYSQL_PASSWORD=${TIDB_RO_PASSWORD}
MYSQL_DB=taobao
MYSQL_SSL=true
EOF
echo "全部完成 ✅"
