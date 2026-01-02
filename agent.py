from typing import Annotated, TypedDict, List, Union
import operator
import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from config import GOOGLE_API_KEY
from config import BASE_URL

from t_invest import return_portfolio

logger = logging.getLogger("agent")

SYS_PROMPT = (
    "You are a financial support agent. Your main task is to carry out high-quality analysis of financial markets.\n"
    "Answer in Russian. Answer only on topics related to financial markets.\n"
    "FORMATTING RULES:\n"
    "1. You must use ONLY these HTML tags: <b>, <i>, <u>, <s>, <code>, <a href='...'>.\n"
    "2. Use the newline character '\\n' for line breaks and paragraphs. Do NOT use tags for structure.\n"
    "3. Do not wrap the whole response in any tags."
    "FORMATTING INSTRUCTIONS:\n"
    "1. Use <b> for headers and key asset names (e.g., <b>Сводный анализ</b>, <b>LKOH</b>).\n"
    "2. Use <code> for ALL monetary values and currencies (e.g., <code>528 615.50 RUB</code>).\n"
    "3. Use lists with dots or emojis for structure, not * or -.\n"
)

@tool
def user_portfolio_info(config: RunnableConfig)->str:
    """
    Получает данные о портфеле пользователя из функции return_portfolio. На основе которых можешь делать анализ и выполнять любые иные действия.
    """
    thread_id = config.get("configurable", {}).get("thread_id", {})
    logger.info(f"Tool 'user_portfolio_info' called for thread_id: {thread_id}")

    try:
        bonds_names = config.get("configurable", {}).get("bonds_names", {})
        data = return_portfolio(bonds_names)
        logger.debug(f"Portfolio data retrieved for {thread_id}")
        return data
    except Exception as e:
        logger.error(f"Error in tool 'user_portfolio_info': {e}")
        return f"Ошибка при получении данных портфеля: {e}"

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    #messages: Annotated[list[AnyMessage], operator.add]

# llm = ChatGoogleGenerativeAI(
#     model="gemini-3-flash-preview",
#     temperature=0,
#     google_api_key=GOOGLE_API_KEY,
# )

llm = init_chat_model(
    "gemini-2.5-flash",
    model_provider="openai",
    api_key=GOOGLE_API_KEY,
    base_url=BASE_URL,
)

tools = [user_portfolio_info]
llm_with_tools = llm.bind_tools(tools)

prompt = ChatPromptTemplate.from_messages([
    ("system", SYS_PROMPT),
    MessagesPlaceholder(variable_name="messages"),
])

def agent_node(state: AgentState):

    messages = state["messages"]

    max_history = 10
    recent_messages = messages[-max_history:] if len(messages) > max_history else messages
    chain = prompt | llm_with_tools

    response = chain.invoke({"messages": recent_messages})

    return {"messages": [response]}

workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
tool_node = ToolNode(tools)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

memory = MemorySaver()

app = workflow.compile(checkpointer=memory)

def agent_answer(user_input: str, user_id: int, bonds_names: dict) -> str:

    config = {
        "configurable": {
            "thread_id": str(user_id), # Уникальный ID диалога
            "bonds_names": bonds_names
        }
    }

    input_data = {"messages": [HumanMessage(content=user_input)]}

    result = app.invoke(input_data, config=config)
    answer = result["messages"][-1]

    return answer.content