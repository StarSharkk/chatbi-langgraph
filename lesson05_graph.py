# 第 5 课：用 LangGraph 把「生成 → 检查 → 执行」连成一张图，加上出错重试
import sys
from typing import TypedDict

import pandas as pd
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from lesson02_generate_sql import generate_sql, knowledge, llm
from lesson03_check_sql import check_sql
from lesson04_run_sql import run_sql

MAX_ATTEMPTS = 3  # 最多让模型写 3 次 SQL（第 1 次 + 最多 2 次修正）


# ---------- State：在节点之间传递的"共享笔记本" ----------
class ChatBIState(TypedDict, total=False):
    question: str            # 用户问题
    sql: str                 # 当前这版 SQL
    error: str               # 上一步的报错（没有报错就是空字符串）
    error_type: str          # "check"=没过安全检查，"sql"=执行报错，"timeout"=超时
    attempts: int            # 已经生成过几次 SQL
    result: pd.DataFrame     # 查询结果
    knowledge: str           # 可选：本次用的知识文本（不传就用完整知识文件）


# 修正用的 prompt：除了问题，还把上一版 SQL 和报错一起给模型
fix_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "你是一名资深数据分析师，负责把业务问题翻译成 MySQL 查询。\n"
     "以下是数据库说明和指标口径，必须严格遵守：\n\n{knowledge}\n\n"
     "输出要求：只输出一条可直接执行的 MySQL SELECT 语句，"
     "不要任何解释，不要用 ``` 包起来。"),
    ("human",
     "问题：{question}\n\n"
     "你上一次写的 SQL：\n{sql}\n\n"
     "它出错了：{error}\n\n"
     "请根据报错修正，重新输出完整的 SQL。"),
])
fix_chain = fix_prompt | llm | StrOutputParser()


# ---------- Node：每个节点读 state，返回要更新的字段 ----------
def generate_node(state: ChatBIState) -> dict:
    attempts = state.get("attempts", 0) + 1
    kb = state.get("knowledge", knowledge)
    if state.get("error"):   # 有报错 → 带着报错去修正
        sql = fix_chain.invoke({"knowledge": kb, "question": state["question"],
                                "sql": state["sql"], "error": state["error"]})
        print(f"\n[generate 第 {attempts} 次，修正上一版的错误]\n{sql}")
    else:                    # 没有报错 → 第一次生成
        sql = generate_sql(state["question"], kb)
        print(f"\n[generate 第 {attempts} 次]\n{sql}")
    return {"sql": sql, "attempts": attempts, "error": "", "error_type": ""}


def check_node(state: ChatBIState) -> dict:
    ok, msg = check_sql(state["sql"])
    if ok:
        print("[check] 通过")
        return {"sql": msg}  # msg 是补过 LIMIT 的 SQL
    print("[check] 不通过：", msg)
    return {"error": msg, "error_type": "check"}


def execute_node(state: ChatBIState) -> dict:
    ok, out = run_sql(state["sql"])
    if ok:
        print(f"[execute] 成功，返回 {len(out)} 行")
        return {"result": out}
    error_type = "timeout" if "execution time exceeded" in out else "sql"
    print(f"[execute] 失败（{error_type}）：", out)
    return {"error": out, "error_type": error_type}


# ---------- Conditional edge：根据 state 决定下一步去哪 ----------
def after_check(state: ChatBIState) -> str:
    if not state.get("error"):
        return "execute"
    return "generate" if state["attempts"] < MAX_ATTEMPTS else "end"


def after_execute(state: ChatBIState) -> str:
    if not state.get("error"):
        return "end"
    if state["error_type"] == "timeout":   # 超时：SQL 本身多半没错，重写也没用
        return "end"
    return "generate" if state["attempts"] < MAX_ATTEMPTS else "end"


# ---------- 把节点和边组装成图 ----------
builder = StateGraph(ChatBIState)
builder.add_node("generate", generate_node)
builder.add_node("check", check_node)
builder.add_node("execute", execute_node)

builder.add_edge(START, "generate")
builder.add_edge("generate", "check")
builder.add_conditional_edges("check", after_check,
                              {"execute": "execute", "generate": "generate", "end": END})
builder.add_conditional_edges("execute", after_execute,
                              {"generate": "generate", "end": END})

graph = builder.compile()


if __name__ == "__main__":
    if sys.argv[1:] == ["--draw"]:
        print(graph.get_graph().draw_mermaid())  # 输出流程图的 Mermaid 代码
        sys.exit()

    if sys.argv[1:] == ["--demo"]:
        # 演示重试：假装上一版 SQL 用了一个不存在的字段，看图会不会自己修好
        start = {"question": "每天的购买次数是多少？",
                 "sql": "SELECT event_date, COUNT(*) FROM ub WHERE behavior_type = 'buy' GROUP BY event_date",
                 "error": "执行出错：(1054, \"Unknown column 'event_date' in 'field list'\")"}
    else:
        question = sys.argv[1] if len(sys.argv) > 1 else "每天的 DAU 是多少？"
        start = {"question": question}

    print("问题：", start["question"])
    final = graph.invoke(start)

    print("\n========== 最终结果 ==========")
    if "result" in final and not final.get("error"):
        print(final["result"])
    else:
        print(f"失败（共尝试 {final['attempts']} 次）：{final['error']}")
