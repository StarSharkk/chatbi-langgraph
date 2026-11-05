# 第 3 课：SQL 安全检查（第二道防线）
# 第一道防线是只读账号；这里在 SQL 发到数据库之前，先用代码把关
import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"ub", "user_rfm"}  # 白名单：只允许查这两张表
MAX_ROWS = 1000                      # 没写 LIMIT 时自动补上，防止一次返回几百万行


def check_sql(sql: str) -> tuple[bool, str]:
    """通过返回 (True, 处理后的 SQL)；不通过返回 (False, 原因)。"""
    # 1. 去掉模型偶尔加的 ``` 包裹和首尾空白
    sql = sql.strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()

    # 2. 解析成语法树：不是合法 SQL 直接拒绝
    try:
        statements = sqlglot.parse(sql, read="mysql")
    except sqlglot.errors.ParseError as e:
        return False, f"SQL 语法错误：{e}"

    # 3. 只允许一条语句（防止 "SELECT ...; DROP TABLE ..." 这种拼接）
    if len(statements) != 1:
        return False, f"只允许一条语句，收到了 {len(statements)} 条"
    tree = statements[0]

    # 4. 最外层必须是查询（SELECT，或 UNION 这类集合查询）
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        return False, f"只允许 SELECT 查询，收到的是 {type(tree).__name__}"

    # 5. 用到的表必须在白名单里（WITH 里自己起名的临时表除外）
    cte_names = {cte.alias for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.db:  # 带库名的写法（如 mysql.user）一律拒绝，只能查当前库 taobao
            return False, f"不允许跨库访问 {table.sql()}"
        if table.name not in cte_names and table.name not in ALLOWED_TABLES:
            return False, f"不允许访问表 {table.sql()}"

    # 6. 禁止导出文件（SELECT ... INTO OUTFILE）
    if tree.find(exp.Into):
        return False, "不允许 SELECT ... INTO"

    # 7. 没有 LIMIT 就补一个
    if not tree.args.get("limit"):
        tree = tree.limit(MAX_ROWS)

    return True, tree.sql(dialect="mysql")


if __name__ == "__main__":
    tests = [
        "SELECT COUNT(*) FROM user_rfm WHERE segment = '重要价值客户'",
        "```sql\nSELECT behavior_type, COUNT(*) FROM ub GROUP BY behavior_type\n```",
        "SELECT * FROM ub LIMIT 5",
        "WITH d25 AS (SELECT DISTINCT user_id FROM ub WHERE d = '2017-11-25') SELECT COUNT(*) FROM d25",
        "SELECT 1; DROP TABLE ub",
        "DELETE FROM ub",
        "SELECT * FROM raw_behavior",
        "SELECT user, host FROM mysql.user",
        "SELEC * FORM ub",
        "SELECT * FROM ub LIMIT 5 #你好",
        "SELECT 1 DRoP TABLE ub",
    ]
    for sql in tests:
        ok, result = check_sql(sql)
        print("✅ 通过" if ok else "❌ 拒绝", "|", sql.replace("\n", " ")[:60])
        print("    →", result)
