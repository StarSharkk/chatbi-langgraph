# 第 6 课：加第 4 个节点 explain，让模型用业务语言解释查询结果
import sys

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from lesson02_generate_sql import knowledge, llm
from lesson03_check_sql import MAX_ROWS
from lesson05_graph import (MAX_ATTEMPTS, ChatBIState, after_check, check_node,
                            execute_node, generate_node)

ROWS_FOR_LLM = 50  # 最多把前 50 行给模型看，结果再大也不会撑爆 prompt


class ExplainState(ChatBIState, total=False):
    answer: str  # 给用户看的业务解释


explain_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "你是一名电商数据分析师，负责向不懂 SQL 的运营同事解释查询结果。\n"
     "以下是数据说明和指标口径：\n\n{knowledge}\n\n"
     "回答要求：\n"
     "1. 先用一句话直接回答问题，给出关键数字；比例写成百分比。\n"
     "2. 再用 1–2 句话说明这个数字的业务含义。\n"
     "3. 只能使用查询结果里出现的数字，结果里没有的数字一律不要编。\n"
     "4. 如果问题涉及留存、付费率，或日期落在 12-02/12-03，要提醒抽样偏差。\n"
     "5. 如果提示结果被截断，要明确告诉用户结果不完整。\n"
     "6. 针对偏差能解释的变化，不要再编业务原因\n"
     "7. 截断时应该建议用户怎么换问法，而不是去改 SQL\n"
     "总共不超过 5 句话。"),
    ("human",
     "问题：{question}\n\n"
     "执行的 SQL：\n{sql}\n\n"
     "查询结果（共 {n_rows} 行{truncated_note}）：\n{table}"),
])
explain_chain = explain_prompt | llm | StrOutputParser()


def explain_node(state: ExplainState) -> dict:
    df = state["result"]
    truncated = len(df) >= MAX_ROWS  # 正好等于 LIMIT，说明很可能还有更多行没取回来
    answer = explain_chain.invoke({
        "knowledge": knowledge,
        "question": state["question"],
        "sql": state["sql"],
        "n_rows": len(df),
        "truncated_note": f"，⚠️ 已达到 {MAX_ROWS} 行上限，结果可能被截断" if truncated else "",
        "table": df.head(ROWS_FOR_LLM).to_string(index=False),
    })
    print("[explain] 完成")
    return {"answer": answer}


def after_execute(state: ExplainState) -> str:
    if not state.get("error"):
        return "explain"                    # 新增：成功后先去解释，再结束
    if state["error_type"] == "timeout":
        return "end"
    return "generate" if state["attempts"] < MAX_ATTEMPTS else "end"


builder = StateGraph(ExplainState)
builder.add_node("generate", generate_node)
builder.add_node("check", check_node)
builder.add_node("execute", execute_node)
builder.add_node("explain", explain_node)

builder.add_edge(START, "generate")
builder.add_edge("generate", "check")
builder.add_conditional_edges("check", after_check,
                              {"execute": "execute", "generate": "generate", "end": END})
builder.add_conditional_edges("execute", after_execute,
                              {"explain": "explain", "generate": "generate", "end": END})
builder.add_edge("explain", END)

graph = builder.compile()


def ask(question: str) -> dict:
    """对外的统一入口：输入问题，返回最终 state（后面的评估和网页都调用它）"""
    return graph.invoke({"question": question})


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "每天的 DAU 是多少？"
    print("问题：", question)
    final = ask(question)

    print("\n========== 回答 ==========")
    if final.get("answer"):
        print(final["answer"])
        print("\n---------- 数据 ----------")
        print(final["result"].head(20).to_string(index=False))
    else:
        print(f"抱歉，没能回答这个问题（共尝试 {final['attempts']} 次）：{final['error']}")
