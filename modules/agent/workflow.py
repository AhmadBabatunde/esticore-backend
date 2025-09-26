"""
Agent workflow and memory management for the Floor Plan Agent API
"""
import uuid
import random
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.graph import MessagesState
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from modules.config.settings import settings
from modules.agent.tools import ALL_TOOLS

# ==============================
# Memory Management
# ==============================

class SimpleChatMessageHistory:
    """Simple chat message history implementation"""
    def __init__(self):
        self.messages = []
    
    def add_message(self, message):
        self.messages.append(message)
    
    def clear(self):
        self.messages = []

class SimpleMemory:
    """Simple memory implementation to store conversation history"""
    def __init__(self):
        self.chat_memory = SimpleChatMessageHistory()
        self.memory_key = "history"
    
    def load_memory_variables(self, inputs):
        return {self.memory_key: "\n".join([str(m) for m in self.chat_memory.messages])}
    
    def save_context(self, inputs, outputs):
        # Extract human input
        human_input = inputs.get("input", "") if isinstance(inputs, dict) else str(inputs)
        # Extract AI output
        ai_output = outputs.get("output", "") if isinstance(outputs, dict) else str(outputs)
        
        if human_input:
            self.chat_memory.add_message(HumanMessage(content=human_input))
        if ai_output:
            self.chat_memory.add_message(AIMessage(content=ai_output))
    
    def clear(self):
        self.chat_memory.clear()

# ==============================
# Chat Session Storage
# ==============================

@dataclass
class ChatMessage:
    """Chat message data structure"""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

class ChatSession:
    """Simple chat session storage"""
    def __init__(self):
        self.sessions = {}
    
    def create_session(self, session_id=None):
        if session_id is None:
            session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "messages": [],
            "created_at": datetime.now(),
            "last_activity": datetime.now()
        }
        return session_id
    
    def add_message(self, session_id, role, content):
        if session_id not in self.sessions:
            self.create_session(session_id)
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        }
        
        self.sessions[session_id]["messages"].append(message)
        self.sessions[session_id]["last_activity"] = datetime.now()
        
        # Keep only the last N messages to prevent memory issues
        if len(self.sessions[session_id]["messages"]) > settings.CHAT_HISTORY_LIMIT:
            self.sessions[session_id]["messages"] = self.sessions[session_id]["messages"][-settings.CHAT_HISTORY_LIMIT:]
    
    def get_messages(self, session_id):
        if session_id in self.sessions:
            return self.sessions[session_id]["messages"]
        return []
    
    def cleanup_old_sessions(self, hours=None):
        """Remove sessions older than specified hours"""
        if hours is None:
            hours = settings.SESSION_CLEANUP_HOURS
            
        now = datetime.now()
        expired_sessions = []
        
        for session_id, session_data in self.sessions.items():
            if (now - session_data["last_activity"]).total_seconds() > hours * 3600:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.sessions[session_id]

# ==============================
# Agent State and Workflow
# ==============================

class FloorPlanState(MessagesState):
    """Represents the state of our floor plan annotation workflow"""
    pdf_path: str
    output_path: str
    annotation_type: str = ""
    temp_image_path: str = ""
    detected_objects: List[Dict] = field(default_factory=list)
    page_number: int = 1

class AgentWorkflow:
    """Agent workflow management"""
    
    def __init__(self):
        self.memory = SimpleMemory()
        self.chat_sessions = ChatSession()
        
        # Initialize agent
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        self.agent = create_tool_calling_agent(self.llm, ALL_TOOLS, self._create_prompt())
        self.agent_executor = AgentExecutor(agent=self.agent, tools=ALL_TOOLS, verbose=True)
        
        # Initialize LangGraph workflow
        self.workflow = self._create_workflow()
        self.compiled_graph = self.workflow.compile()
    
    def _create_prompt(self):
        """Create the agent prompt template"""
        return ChatPromptTemplate.from_messages([
            ("system", """You are an expert Civil Engeneering AI assistant for working with floor plan documents. You can both answer questions about the documents and annotate specific pages.

**Workflow for Annotation Requests:**
1.  **Load & Validate PDF**: Use `load_pdf_for_floorplan` to check the PDF.
2.  **Convert Specific Page to Image**: Use `convert_pdf_page_to_image` with the specified page number.
3.  **Detect Objects**: Use `detect_floor_plan_objects` to get a JSON list of all objects and their bounding boxes.
4.  **Verify Detections (If Needed)**: If the user asks for a specific object type, call `verify_detections` to check if that object type was found.
5.  **Apply Annotation**: Call the appropriate annotation tool based on the user's request.
6.  **Save Final PDF**: ALWAYS use `save_annotated_image_as_pdf_page` to save the annotated page and merge it with the original PDF. Use the output_path from the state.

**Workflow for Question Answering:**
1.  **Answer Questions with Suggestions**: ALWAYS use `answer_question_with_suggestions` to answer questions about the document content and provide related topic suggestions with page numbers. This returns structured JSON.
2.  **Fallback**: Only use `answer_question_using_rag` if the enhanced function fails.

**Internet Search Capability:**
- When the user asks for up-to-date information or facts that cannot be found in the document (e.g., current market trends, recent news, latest regulations, factual data not in the document), use the `internet_search` tool to retrieve current information.
- Always cite the sources from the internet search results when providing answers.

**Important for Questions**: When answering questions, you MUST use `answer_question_with_suggestions` and return its JSON output directly without modification.

**Intent Detection:**
- If the user asks a question about the document content (e.g., "what's on page 3", "tell me about the kitchen"), use the RAG tool.
- If the user requests an annotation (e.g., "highlight doors on page 2", "circle all windows"), follow the annotation workflow.
- If the user asks for current information or facts not contained in the document, use the internet_search tool.
- If the user's intent is unclear, ask for clarification.

**Crucial Instructions:**
- Always determine the user's intent first.
- For annotation requests, follow the complete sequence INCLUDING the save step.
- ALWAYS call `save_annotated_image_as_pdf_page` at the end of any annotation workflow.
- For question answering, use the RAG tool directly.
- When a user asks to annotate specific items, verify the detections first.
- Only call one annotation tool per request.
- The final output for annotation should be a complete PDF with only the specified page annotated.
- When saving, use the exact output_path provided in the state.

**State Information:**
You have access to:
- pdf_path: The path to the original PDF
- page_number: The specific page to work on
- output_path: Where to save the final annotated PDF (ALWAYS use this exact path)
"""),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
    
    def _create_workflow(self):
        """Create the LangGraph workflow"""
        def should_continue(state: FloorPlanState) -> str:
            return "action" if state["messages"][-1].tool_calls else END

        def call_agent(state: FloorPlanState):
            # Add memory context to the state
            memory_context = self.memory.load_memory_variables({})
            
            # Create a more detailed message that includes state information
            original_message = state["messages"][-1].content if state["messages"] else ""
            
            # Add state context to help the agent understand what it needs to do
            context_message = f"""
            CURRENT STATE CONTEXT:
            - PDF Path: {state.get('pdf_path', 'Not set')}
            - Page Number: {state.get('page_number', 'Not set')}
            - Output Path: {state.get('output_path', 'Not set')}
            
            USER REQUEST: {original_message}
            
            IMPORTANT: If this is an annotation request, you MUST call save_annotated_image_as_pdf_page at the end with:
            - image_path: the temporary image path from convert_pdf_page_to_image
            - original_pdf_path: {state.get('pdf_path', '')}
            - page_number: {state.get('page_number', 1)}
            - output_pdf_path: {state.get('output_path', '')}
            """
            
            # Update the state with the context message
            state_with_context = state.copy()
            state_with_context["messages"] = state["messages"][:-1] + [HumanMessage(content=context_message)]
            
            if memory_context and "history" in memory_context and memory_context["history"]:
                # Add memory to the conversation
                state_with_context["messages"].append(HumanMessage(content=f"Memory context: {memory_context['history']}"))
            
            response = self.agent_executor.invoke(state_with_context)
            
            # Save to memory
            self.memory.save_context({"input": original_message}, {"output": response["output"]})
            
            return {"messages": [AIMessage(content=response["output"])]}

        workflow = StateGraph(FloorPlanState)
        workflow.add_node("agent", call_agent)
        workflow.add_node("action", ToolNode(ALL_TOOLS))
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", should_continue, {"action": "action", END: END})
        workflow.add_edge("action", "agent")
        
        return workflow
    
    def process_request(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Process a request through the agent workflow"""
        try:
            final_state = self.compiled_graph.invoke(initial_state, {"recursion_limit": settings.RECURSION_LIMIT})
            return final_state
        except Exception as e:
            raise Exception(f"Agent workflow error: {str(e)}")
    
    def get_or_create_chat_session(self, session_id: str = None) -> str:
        """Get or create a chat session"""
        if random.random() < 0.1:  # 10% chance on each request
            self.chat_sessions.cleanup_old_sessions()
        
        if not session_id:
            session_id = self.chat_sessions.create_session()
        elif session_id not in self.chat_sessions.sessions:
            self.chat_sessions.create_session(session_id)
        
        return session_id
    
    def add_chat_message(self, session_id: str, role: str, content: str):
        """Add a message to chat session"""
        self.chat_sessions.add_message(session_id, role, content)
    
    def get_chat_history(self, session_id: str) -> List[Dict]:
        """Get chat history for a session"""
        return self.chat_sessions.get_messages(session_id)

# Global agent workflow instance
agent_workflow = AgentWorkflow()