# 第 7 课：评估集，用"执行准确率"给 ChatBI 打分，并对比不同知识版本
import argparse
import hashlib
import contextlib
import io
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from lesson02_generate_sql import knowledge
from lesson04_run_sql import run_sql
from lesson05_graph import graph  # 评估只测"写 SQL"，不走 explain，省时间省钱

HERE = Path(__file__).parent
EVAL_DIR = HERE / "eval"


# ---------- 两个知识版本：A/B 对比"指标口径"到底有没有用 ----------
def drop_sections(text: str, titles: list[str]) -> str:
    """去掉知识文件里指定标题的整节（## 开头的段落）"""
    parts = re.split(r"(?m)^(?=## )", text)
    return "".join(p for p in parts if not any(p.startswith(f"## {t}") for t in titles))


VARIANTS = {
    "full": knowledge,                                              # 表结构 + 指标口径
    "schema_only": drop_sections(knowledge, ["指标口径", "已知数据偏差"]),  # 只有表结构
}


# ---------- 判分：参考答案里的每个值，都要在 ChatBI 的结果里找到 ----------
def to_value(v):
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float, Decimal)) or hasattr(v, "dtype"):
        try:
            return float(v)
        except (TypeError, ValueError):
            pass
    return str(v).strip()


def close(a: float, ref: float) -> bool:
    if ref == int(ref) and abs(ref) > 1:      # 人数、次数这类整数：必须完全相等
        return a == ref
    # 比例：允许 0.5% 的相对误差，也接受写成百分数（72.13 对 0.7213）
    return any(abs(c - ref) <= max(abs(ref) * 0.005, 5e-4) for c in (a, a / 100))


def is_correct(pred: pd.DataFrame, ref: pd.DataFrame) -> bool:
    pred_vals = [to_value(v) for v in pred.to_numpy().ravel()]
    ref_vals = [to_value(v) for v in ref.to_numpy().ravel()]
    # 参考答案里有数字时只比数字：'pv' 这类标签换成"浏览"或变成列名，答案依然算对
    if any(isinstance(v, float) for v in ref_vals):
        ref_vals = [v for v in ref_vals if isinstance(v, float)]
    for rv in ref_vals:
        if isinstance(rv, float):
            ok = any(isinstance(p, float) and close(p, rv) for p in pred_vals)
        else:
            ok = rv in pred_vals
        if not ok:
            return False
    return True


# ---------- 跑一道题 ----------
def run_one(item: dict, variant: str, ref: pd.DataFrame) -> dict:
    t0 = time.time()
    try:
        final = graph.invoke({"question": item["question"], "knowledge": VARIANTS[variant]})
    except Exception as e:  # 模型接口出错等意外，记为失败
        final = {"error": f"{type(e).__name__}: {e}", "attempts": 0}
    executed = "result" in final and not final.get("error")
    correct = executed and is_correct(final["result"], ref)
    return {
        "id": item["id"], "level": item["level"], "variant": variant,
        "executed": executed, "correct": correct,
        "first_try": correct and final.get("attempts") == 1,
        "attempts": final.get("attempts", 0),
        "seconds": round(time.time() - t0, 1),
        "sql": final.get("sql", ""), "error": final.get("error", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", nargs="+", default=list(VARIANTS))
    parser.add_argument("--repeats", type=int, default=2, help="每道题重复几次（LLM 有随机性）")
    parser.add_argument("--ids", type=str, default="", help="只跑部分题目，如 1,2,3")
    parser.add_argument("--set", default="eval_set", help="题库文件名（eval/ 下，不带 .json）")
    parser.add_argument("--workers", type=int, default=4, help="同时跑几道题")
    args = parser.parse_args()

    items = json.loads((EVAL_DIR / f"{args.set}.json").read_text(encoding="utf-8"))
    if args.ids:
        keep = {int(i) for i in args.ids.split(",")}
        items = [it for it in items if it["id"] in keep]

    print(f"计算 {len(items)} 道题的参考答案……", file=sys.stderr)
    refs = {}
    for it in items:
        ok, ref = run_sql(it["ref_sql"])
        if not ok:
            sys.exit(f"第 {it['id']} 题的参考 SQL 出错：{ref}")
        refs[it["id"]] = ref

    jobs = [(it, v) for v in args.variants for it in items for _ in range(args.repeats)]
    print(f"开始评估：{len(jobs)} 次运行（{args.workers} 个并行）", file=sys.stderr)
    rows = []
    # 节点里的 print 会刷屏：评估期间把标准输出整体丢掉（进度写在 stderr，不受影响）
    with contextlib.redirect_stdout(io.StringIO()), ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, it, v, refs[it["id"]]) for it, v in jobs]
        for i, f in enumerate(futures, 1):
            r = f.result()
            rows.append(r)
            mark = "✅" if r["correct"] else ("⚠️ 结果不对" if r["executed"] else "❌ 执行失败")
            print(f"[{i}/{len(jobs)}] {r['variant']:<12} 第{r['id']:>2}题 {mark}", file=sys.stderr)

    df = pd.DataFrame(rows)
    out = EVAL_DIR / f"results_{args.set}_{datetime.now():%Y%m%d_%H%M}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print("\n========== 总体 ==========")
    summary = df.groupby("variant").agg(
        准确率=("correct", "mean"), 一次就对=("first_try", "mean"),
        能执行=("executed", "mean"), 平均尝试次数=("attempts", "mean"), 平均秒数=("seconds", "mean"),
    )
    print(summary.round(3).to_string())
    print("\n========== 按题型的准确率 ==========")
    print(df.pivot_table(index="level", columns="variant", values="correct", aggfunc="mean").round(3).to_string())
    print("\n========== 答错的题 ==========")
    wrong = df[~df["correct"]].groupby(["variant", "id"]).size()
    print(wrong.to_string() if len(wrong) else "无")
    # 知识文件"指纹"：内容改过一个字，这串就会变。用来证明测试期间知识没被偷偷改过
    print(f"\n知识文件指纹：{hashlib.md5(knowledge.encode()).hexdigest()[:8]}")
    print(f"明细已保存：{out}")


if __name__ == "__main__":
    main()
