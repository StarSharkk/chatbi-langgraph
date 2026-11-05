# 第 4 课：用只读账号执行 SQL，并把「生成 → 检查 → 执行」串起来
import os
import sys
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv

from lesson02_generate_sql import generate_sql
from lesson03_check_sql import check_sql

load_dotenv(Path(__file__).parent / ".env")

TIMEOUT_MS = 30_000  # 单条查询最多跑 30 秒，超时由 MySQL 自己中断


def run_sql(sql: str) -> tuple[bool, pd.DataFrame | str]:
    """成功返回 (True, 结果表)；失败返回 (False, 报错信息)。报错信息下一课要喂回给模型。"""
    try:
        conn = pymysql.connect(
            host=os.getenv("MYSQL_HOST"),
            port=int(os.getenv("MYSQL_PORT")),
            user=os.getenv("MYSQL_USER"),          # chatbi_ro：第一道防线，只读账号
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DB"),
            charset="utf8mb4",
        )
    except pymysql.MySQLError as e:
        return False, f"连接数据库失败：{e}"

    try:
        with conn.cursor() as cur:
            cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {TIMEOUT_MS}")
            cur.execute(sql)
            columns = [col[0] for col in cur.description]
            return True, pd.DataFrame(cur.fetchall(), columns=columns)
    except pymysql.MySQLError as e:
        return False, f"执行出错：{e}"
    finally:
        conn.close()  # 不管成功失败都关掉连接


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "每种行为类型各有多少条记录？"
    print("问题：", question)

    sql = generate_sql(question)          # 第 1 步：生成
    print("\n[生成的 SQL]\n", sql)

    ok, checked = check_sql(sql)          # 第 2 步：检查
    if not ok:
        print("\n[检查不通过]", checked)
        sys.exit()
    print("\n[检查后的 SQL]\n", checked)

    ok, result = run_sql(checked)         # 第 3 步：执行
    print("\n[执行结果]" if ok else "\n[执行失败]")
    print(result)
