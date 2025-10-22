"""
Agent workflow and memory management for the Floor Plan Agent API
"""
from __future__ import annotations

import uuid
import random
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph import MessagesState
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from modules.config.settings import settings
from modules.agent.tools import (
    load_pdf_for_floorplan,
    convert_pdf_page_to_image,
    detect_floor_plan_objects,
    verify_detections,
    internet_search,
    generate_frontend_annotations,
    answer_question_using_rag,
    answer_question_with_suggestions,
    analyze_pdf_page_multimodal,
    measure_objects,
    calibrate_scale,
    analyze_object_proportions,
    clean_temp_image,
)

# All tools must be LangChain Tools (BaseTool / StructuredTool or @tool) for ToolNode
ALL_TOOLS = [
    load_pdf_for_floorplan,
    convert_pdf_page_to_image,
    detect_floor_plan_objects,
    verify_detections,
    internet_search,
    generate_frontend_annotations,
    answer_question_using_rag,
    answer_question_with_suggestions,
    analyze_pdf_page_multimodal,
    measure_objects,
    calibrate_scale,
    analyze_object_proportions,
    clean_temp_image,
]

from modules.session import session_manager, context_resolver
from modules.database import db_manager


# -----------------------------
# Simple memory (fallback only)
# -----------------------------
class SimpleChatMessageHistory:
    def __init__(self):
        self.messages: List[Any] = []

    def add_message(self, message: Any):
        self.messages.append(message)

    def clear(self):
        self.messages = []


class SimpleMemory:
    def __init__(self):
        self.chat_memory = SimpleChatMessageHistory()
        self.memory_key = "history"

    def load_memory_variables(self, inputs):
        return {self.memory_key: "\n".join([str(m) for m in self.chat_memory.messages])}

    def save_context(self, inputs, outputs):
        human_input = inputs.get("input", "") if isinstance(inputs, dict) else str(inputs)
        ai_output = outputs.get("output", "") if isinstance(outputs, dict) else str(outputs)
        if human_input:
            self.chat_memory.add_message(HumanMessage(content=human_input))
        if ai_output:
            self.chat_memory.add_message(AIMessage(content=ai_output))

    def clear(self):
        self.chat_memory.clear()


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


# -----------------------------
# LangGraph State
# -----------------------------
class FloorPlanState(MessagesState):
    pdf_path: str
    output_path: str
    annotation_type: str = ""
    temp_image_path: str = ""
    detected_objects: List[Dict] = field(default_factory=list)
    page_number: int = 1
    session_id: str | None = None
    user_id: int | None = None


# -----------------------------
# Agent Workflow
# -----------------------------
class AgentWorkflow:
    def __init__(self):
        self.memory = SimpleMemory()
        self.session_manager = session_manager
        self.context_resolver = context_resolver

        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0.0,
            api_key=settings.OPENAI_API_KEY,
        )
        # Build the LCEL chain once: prompt -> llm with tools
        self.prompt = self._create_prompt()
        self.llm_with_tools = self.llm.bind_tools(ALL_TOOLS)
        self.chain = self.prompt | self.llm_with_tools

        self.workflow = self._create_workflow()
        self.compiled_graph = self.workflow.compile()

    def _create_prompt(self):
        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an expert Civil Engineering AI assistant specializing in floor plan documents. Your primary role is to accurately analyze user requests and select the most appropriate tool to fulfill their goal. Follow the decision-making process based on the user's intent.

**ANNOTATION (highlight/circle/annotate/mark/count)** → 2 steps:
  1) convert_pdf_page_to_image → detect_floor_plan_objects
  2) generate_frontend_annotations with detections
Final output MUST be the raw JSON from generate_frontend_annotations (no extra text). If nothing matches a filter, reply conversationally and suggest detected types. Use clean_temp_image to clean temp image.

**MEASUREMENT (measure/how wide/tall/size/dimensions)**:
  detect_floor_plan_objects → measure_objects; reply with clear numeric values + units.

**VISUAL ANALYSIS (describe layout/where located/appearance/spatial)**:
  Prefer analyze_pdf_page_multimodal.

**TEXT Q&A (specifications/notes/legend/explain)**:
  Default to answer_question_with_suggestions.

**EXTERNAL INFO (latest/current/regulation/price/law/code/standard)**:
  Use internet_search.

Rules:
- Annotation final response = JSON from generate_frontend_annotations only.
- No file paths or download links.
- Don’t mix workflows.
""",
                ),
                MessagesPlaceholder(variable_name="messages"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

    def _create_workflow(self):
        def should_continue(state: FloorPlanState) -> str:
            last = state["messages"][-1] if state["messages"] else None
            return "action" if getattr(last, "tool_calls", None) else END

        def call_agent(state: FloorPlanState):
            # Build history (optional)
            session_id = state.get("session_id")
            user_id = state.get("user_id")
            history_text = ""
            if session_id and user_id is not None:
                try:
                    history_msgs = self.get_chat_history(session_id, user_id, limit=20)
                    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history_msgs])
                except Exception as e:
                    print(f"DEBUG: Error loading session history: {e}")

            original_message = state["messages"][-1].content if state.get("messages") else ""

            prompt_text = f"""
PREVIOUS CONVERSATION:
{history_text}

CURRENT TASK:
- PDF Path: {state.get('pdf_path', 'Not set')}
- Page Number: {state.get('page_number', 'Not set')}
- User Request: {original_message}

Remember: For annotation → (convert_pdf_page_to_image → detect_floor_plan_objects) → generate_frontend_annotations. Final output must be JSON for annotation requests.
""".strip()

            ai_msg: AIMessage = self.chain.invoke({"messages": [HumanMessage(content=prompt_text)]})

            # Persist assistant output (content only)
            if session_id and user_id is not None:
                try:
                    self.add_chat_message(session_id, "assistant", ai_msg.content, user_id)
                except Exception as e:
                    print(f"DEBUG: Error saving assistant message to session: {e}")
            else:
                self.memory.save_context({"input": original_message}, {"output": ai_msg.content})

            return {"messages": [ai_msg]}

        graph = StateGraph(FloorPlanState)
        graph.add_node("agent", call_agent)
        graph.add_node("action", ToolNode(ALL_TOOLS))
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", should_continue, {"action": "action", END: END})
        graph.add_edge("action", "agent")
        return graph

    def process_request(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_message = initial_state["messages"][-1].content if initial_state.get("messages") else ""
            msg_lower = user_message.lower()
            if any(x in msg_lower for x in ["highlight", "circle", "rectangle", "count", "arrow", "annotate"]):
                intent = "annotation"
            elif any(x in msg_lower for x in ["latest", "current", "recent", "news", "trend", "regulation", "countries", "can i build", "allowed", "permitted", "legal", "law", "code", "standard"]):
                intent = "internet_search"
            elif any(x in msg_lower for x in ["describe", "show", "visual", "layout", "diagram", "where", "located", "appearance", "spatial", "look", "see", "view", "display"]):
                intent = "visual_analysis"
            else:
                intent = "question"

            final_state = self.compiled_graph.invoke(
                initial_state,
                {"recursion_limit": settings.RECURSION_LIMIT, "intent": intent},
            )
            return final_state
        except Exception as e:
            raise Exception(f"Agent workflow error: {str(e)}")

    def get_or_create_chat_session(
        self,
        session_id: str | None = None,
        user_id: int | None = None,
        context_type: str = "GENERAL",
        context_id: str | None = None,
    ) -> str:
        if random.random() < settings.SESSION_ACTIVITY_UPDATE_PROBABILITY:
            self.session_manager.cleanup_expired_sessions()

        if session_id:
            session = self.session_manager.get_session_by_id(session_id)
            if session and session.is_active:
                self.session_manager.update_session_activity(session_id)
                return session_id

        if user_id is not None:
            return self.session_manager.get_or_create_session(user_id, context_type, context_id)

        return str(uuid.uuid4())

    def get_or_create_context_session(self, user_id: int, context_data: Dict[str, Any]) -> str:
        context_type, context_id = self.context_resolver.resolve_context(context_data)
        return self.session_manager.get_or_create_session(user_id, context_type, context_id)

    def add_chat_message(self, session_id: str, role: str, content: str, user_id: int | None = None):
        if user_id is not None:
            success = self.session_manager.add_message_to_session(session_id, user_id, role, content)
            if not success:
                print(f"Warning: Failed to add message to session {session_id}")
        else:
            if hasattr(self, "chat_sessions"):
                self.chat_sessions.add_message(session_id, role, content)

    def get_chat_history(self, session_id: str, user_id: int | None = None, limit: int = 50) -> List[Dict]:
        if user_id is not None:
            messages = db_manager.get_chat_history(user_id, session_id, limit)
            return [
                {"role": msg.role, "content": msg.message, "timestamp": msg.timestamp}
                for msg in reversed(messages)
            ]
        else:
            if hasattr(self, "chat_sessions"):
                return self.chat_sessions.get_messages(session_id)
            return []

    def get_session_context(self, session_id: str) -> tuple:
        return self.session_manager.get_session_context(session_id)

    def validate_session_access(self, session_id: str, user_id: int) -> bool:
        return self.session_manager.validate_session_access(session_id, user_id)


# Global instance
agent_workflow = AgentWorkflow()
