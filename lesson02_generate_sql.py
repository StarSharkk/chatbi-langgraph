# 第 2 课：把「表结构 + 指标口径」放进 prompt，让模型只输出一条 SQL
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL"),
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    temperature=0,
)

# 知识文件：表结构和指标口径都写在这里，改口径不用改代码
knowledge = (HERE / "knowledge" / "schema_and_metrics.md").read_text(encoding="utf-8")

# Prompt 模板：system 放"规则和知识"，human 放"用户问题"
# {knowledge} 和 {question} 是占位符，调用时再填进去
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "你是一名资深数据分析师，负责把业务问题翻译成 MySQL 查询。\n"
     "以下是数据库说明和指标口径，必须严格遵守：\n\n{knowledge}\n\n"
     "输出要求：只输出一条可直接执行的 MySQL SELECT 语句，"
     "不要任何解释，不要用 ``` 包起来。"),
    ("human", "{question}"),
])

# LCEL：用 | 把三步串成一条链：填模板 → 调模型 → 取出纯文本
chain = prompt | llm | StrOutputParser()


def generate_sql(question: str, kb: str = knowledge) -> str:
    """把业务问题翻译成一条 SQL（其他文件可以 import 这个函数）
    kb 默认用完整知识文件；评估时可以换成别的版本做对比"""
    return chain.invoke({"knowledge": kb, "question": question})


# 只有直接运行本文件时才执行下面的代码；被别的文件 import 时不执行
if __name__ == "__main__":
    # 命令行里给了问题就用它，没给就用默认问题
    question = sys.argv[1] if len(sys.argv) > 1 else "淘宝数据里，加购过的用户有多少比例最后购买了？"
    print(generate_sql(question))
