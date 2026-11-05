#!/bin/bash
# 给 ub 表加一份列存副本（TiFlash），让大表聚合走列存 + MPP，减少行存聚合爆内存
# 用法（在 chatbi 文件夹里）：bash deploy/enable_tiflash.sh
set -euo pipefail
cd "$(dirname "$0")"
source ../.env.tidb

CNF=$(mktemp)
chmod 600 "$CNF"
trap 'rm -f "$CNF"' EXIT
printf '[client]\npassword=%s\n' "$TIDB_PASSWORD" > "$CNF"

tidb() {
  /usr/local/mysql/bin/mysql --defaults-extra-file="$CNF" \
    -h "$TIDB_HOST" -P "$TIDB_PORT" -u "$TIDB_USER" \
    --ssl-mode=VERIFY_IDENTITY --ssl-ca=/etc/ssl/cert.pem "$@"
}

tidb taobao -e "ALTER TABLE ub SET TIFLASH REPLICA 1; ALTER TABLE user_rfm SET TIFLASH REPLICA 1;"
echo "已提交，等待列存副本同步（PROGRESS 到 1 才算完成）……"
for i in $(seq 1 60); do
  tidb -N -e "SELECT TABLE_NAME, AVAILABLE, PROGRESS FROM information_schema.tiflash_replica WHERE TABLE_SCHEMA='taobao'"
  if [ "$(tidb -N -e "SELECT MIN(AVAILABLE) FROM information_schema.tiflash_replica WHERE TABLE_SCHEMA='taobao'")" = "1" ]; then
    echo "列存副本已就绪 ✅"
    exit 0
  fi
  sleep 20
done
echo "20 分钟内还没同步完，可以稍后再运行本脚本查看进度"
