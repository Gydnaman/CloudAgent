from dataclasses import replace
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.auth.context import DemoRunContext
from app.knowledge.mock import MockKnowledgeProvider
from app.providers.mock import LLMRequest, MockLLMProvider
from app.tools.mock import MockToolProvider


class AgentState(TypedDict, total=False):
    intent: str
    answer: str
    source_ids: list[str]


FOLLOW_UP_MARKERS = ("还支持别的吗", "还有吗", "还有呢", "具体一点", "详细一点", "那呢", "这个呢")


def route_question(question: str, history: list[str] | None = None) -> str:
    if "用量" in question and any(word in question for word in ("查询", "查看", "多少")):
        return "billing"
    if any(word in question for word in ("产品", "部署", "版本", "兼容")):
        return "product"
    if history and any(marker in question for marker in FOLLOW_UP_MARKERS):
        for previous_question in reversed(history):
            previous_intent = route_question(previous_question)
            if previous_intent != "unsupported":
                return previous_intent
    return "unsupported"


class AgentRuntime:
    def __init__(self, checkpointer: object):
        self.knowledge = MockKnowledgeProvider()
        self.tools = MockToolProvider()
        self.llm = MockLLMProvider()
        graph = StateGraph(AgentState, context_schema=DemoRunContext)
        graph.add_node("route", self.route)
        graph.add_node("work", self.work)
        graph.add_node("respond", self.respond)
        graph.add_edge(START, "route")
        graph.add_conditional_edges("route", lambda state: "respond" if state["intent"] == "unsupported" else "work")
        graph.add_edge("work", "respond")
        graph.add_edge("respond", END)
        self.graph = graph.compile(checkpointer=checkpointer)

    async def route(self, state: AgentState, runtime: Runtime[DemoRunContext]) -> dict:
        intent = route_question(runtime.context.question, list(runtime.context.history))
        if intent == "unsupported":
            await runtime.context.emit("route.unsupported", {"intent": intent})
        else:
            await runtime.context.emit("route.selected", {"intent": intent})
        return {"intent": intent}

    async def work(self, state: AgentState, runtime: Runtime[DemoRunContext]) -> dict:
        intent = state["intent"]
        question = runtime.context.question
        history = runtime.context.history
        await runtime.context.emit("agent.started", {"agent": intent})
        if intent == "product":
            query = question
            if any(marker in query for marker in FOLLOW_UP_MARKERS) and history:
                query = next((item for item in reversed(history) if route_question(item) == "product"), query)
            evidence = await self.knowledge.search(query, {}, runtime.context.subject)
            if not evidence:
                await runtime.context.emit("knowledge.empty", {"source": "mock"})
                return {"answer": "DEMO / MOCK：没有匹配的演示资料，无法确认该产品信息。", "source_ids": []}
            await runtime.context.emit("knowledge.search.completed", {"sources": [item.source_id for item in evidence]})
            return {"answer": f"DEMO / MOCK：{evidence[0].summary} 来源：{evidence[0].source_id}。", "source_ids": [evidence[0].source_id]}
        other = any(word in question for word in ("其他", "别人", "他人"))
        account_id = "acct-bob" if runtime.context.subject.account_id != "acct-bob" else "acct-alice"
        if not other:
            account_id = runtime.context.subject.account_id
        result = await self.tools.invoke("read_account_usage", {"account_id": account_id}, runtime.context.subject)
        await runtime.context.emit("tool.authorization", {"tool": "read_account_usage", "decision": "allow" if result["allowed"] else "deny", "reason": result.get("reason")})
        if not result["allowed"]:
            await runtime.context.emit("tool.skipped", {"tool": "read_account_usage", "reason": result["reason"]})
            return {"answer": "DEMO / MOCK：该账户不属于当前演示身份，工具未执行。"}
        await runtime.context.emit("tool.completed", {"tool": "read_account_usage", "summary": result["summary"]})
        return {"answer": f"DEMO / MOCK：本账户 {result['summary']['period']} 用量为 {result['summary']['units']} {result['summary']['unit']}。"}

    async def respond(self, state: AgentState, runtime: Runtime[DemoRunContext]) -> dict:
        answer = state.get("answer", "DEMO / MOCK：请说明您要咨询产品部署版本还是查询账户用量。")
        if "工具未执行" not in answer:
            async for chunk in self.llm.stream(LLMRequest(answer)):
                await runtime.context.emit("llm.delta", {"text": chunk.text, "source": "mock"})
        return {"answer": answer}

    async def invoke(self, question: str, history: list[str], context: DemoRunContext, run_id: str) -> AgentState:
        run_context = replace(context, question=question, history=tuple(history))
        return await self.graph.ainvoke({}, config={"configurable": {"thread_id": run_id}}, context=run_context)
