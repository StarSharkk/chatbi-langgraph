# 第 8 课：Streamlit 网页界面（运行：streamlit run app.py）
import os
from datetime import date

import pandas as pd
import streamlit as st

from lesson06_explain import graph

st.set_page_config(page_title="淘宝 ChatBI", page_icon="📊", layout="wide")
st.title("📊 淘宝用户行为 ChatBI")
st.caption("用中文提问，自动生成 SQL → 安全检查 → 只读执行 → 业务解释。"
           "数据：2017-11-25 至 12-03，10% 用户抽样。")

# ---------- 部署到公网时的防滥用：访问密码 + 每个会话的提问上限 ----------
# 每次提问都花你的 DeepSeek 余额，所以公开部署时一定要设 APP_PASSWORD
APP_PASSWORD = os.getenv("APP_PASSWORD")
MAX_QUESTIONS = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "20"))

if APP_PASSWORD and not st.session_state.get("authed"):
    pw = st.text_input("请输入访问密码", type="password")
    if pw == APP_PASSWORD:
        st.session_state.authed = True
        st.rerun()
    if pw:
        st.error("密码不正确")
    st.stop()  # 没通过就不渲染下面的内容

NODE_NAMES = {"generate": "生成 SQL", "check": "安全检查", "execute": "执行查询", "explain": "解释结果"}
EXAMPLES = ["每天的 DAU 是多少？", "复购率是多少？", "加购过的用户有多少比例最后购买了？",
            "一天中哪个小时的购买转化率最高？", "各个 RFM 分层分别有多少人？"]


def to_chart_data(df: pd.DataFrame) -> pd.DataFrame | None:
    """第一列当横轴、其余数值列当纵轴；不适合画图就返回 None"""
    if len(df.columns) < 2 or not 2 <= len(df) <= 50:
        return None
    data = df.set_index(df.columns[0])
    data = data.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    if data.empty:
        return None
    data.index = data.index.astype(str)  # 类目 ID 当成标签，不当成数字
    return data


def run(question: str):
    """用 graph.stream 逐个节点地跑，边跑边把进度显示在页面上"""
    final = {"question": question}
    with st.status("思考中……", expanded=True) as status:
        for chunk in graph.stream({"question": question}, stream_mode="updates"):
            for node, update in chunk.items():   # 每完成一个节点，拿到它返回的更新
                final.update(update)
                if update.get("error"):
                    st.write(f"⚠️ {NODE_NAMES[node]}：{update['error'][:120]}")
                else:
                    st.write(f"✅ {NODE_NAMES[node]}")
        ok = bool(final.get("answer"))
        status.update(label=f"完成（生成 SQL {final.get('attempts', 0)} 次）" if ok else "没能回答",
                      state="complete" if ok else "error", expanded=not ok)
    return final


# ---------- 页面 ----------
cols = st.columns(len(EXAMPLES))
clicked = next((q for c, q in zip(cols, EXAMPLES) if c.button(q, use_container_width=True)), None)
question = st.chat_input("例如：加购后 24 小时内购买的占比是多少？") or clicked

# Streamlit 每次交互都会把整个脚本从头跑一遍，普通变量会被清空；
# st.session_state 是跨刷新保留的"记事本"，聊天记录存在这里
if "history" not in st.session_state:
    st.session_state.history = []  # 每一项：{"question": 问题, "final": 图的最终 state}


def show_answer(final: dict):
    """画出一条回答：解释 → 图表 → 数据表 → SQL"""
    if final.get("answer"):
        st.markdown(final["answer"])
        df = final["result"]
        chart = to_chart_data(df)
        if chart is not None:
            if isinstance(df.iloc[0, 0], date):   # 横轴是日期 → 折线图，否则柱状图
                st.line_chart(chart)
            else:
                st.bar_chart(chart)
        st.dataframe(df, use_container_width=True, hide_index=True)
        with st.expander("查看执行的 SQL"):
            st.code(final["sql"], language="sql")
    else:
        st.error(f"抱歉，没能回答这个问题：{final.get('error', '未知错误')}")
        if final.get("sql"):
            with st.expander("最后一版 SQL"):
                st.code(final["sql"], language="sql")


# 先把历史问答重新画一遍（不会重新调用模型，只是展示存下来的结果）
for turn in st.session_state.history:
    st.chat_message("user").write(turn["question"])
    with st.chat_message("assistant"):
        show_answer(turn["final"])

if question and len(st.session_state.history) >= MAX_QUESTIONS:
    st.warning(f"本次会话已达到 {MAX_QUESTIONS} 个问题的上限，请刷新页面后再试。")
    question = None

if question:
    st.chat_message("user").write(question)
    with st.chat_message("assistant"):
        final = run(question)
        show_answer(final)
    st.session_state.history.append({"question": question, "final": final})

if st.session_state.history and st.sidebar.button("🗑️ 清空对话"):
    st.session_state.history = []
    st.rerun()
