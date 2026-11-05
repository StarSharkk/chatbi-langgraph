# 第 1 课：用 LangChain 调用 DeepSeek，确认模型能通
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()  # 读取 .env，把里面的值放进环境变量（Key 不写在代码里）

llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL"),         # deepseek-flash
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",  # DeepSeek 兼容 OpenAI 接口，只需改地址
    temperature=0,                        # 0 = 输出尽量稳定，写 SQL 不需要"创意"
)

resp = llm.invoke("淘宝数据里，加购过的用户有多少比例最后购买了？写一条 MySQL 查询。")
print(resp.content)
print(resp.usage_metadata)  # 这次调用用了多少

# token（= 花了多少钱）
