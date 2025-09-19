"""
Agent workflow and memory management for the Floor Plan Agent API
"""
import uuid
import random
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent, ToolNode
from langgraph.graph import StateGraph, MessagesState, END
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
        self.chat_sessions = ChatSession()
        
        # Initialize memory manager for long-term memory
        from modules.config.memory import MemoryManager
        self.memory_manager = MemoryManager()
        
        # Initialize agent with React pattern and memory tools
        self.llm = ChatOpenAI(model="gpt-5", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        self.agent_executor = create_react_agent(
            self.llm,
            tools=ALL_TOOLS + self.memory_manager.get_memory_tools(),
            store=self.memory_manager.get_store(),
            prompt=self._create_prompt()
        )
        
        # Initialize LangGraph workflow
        self.workflow = self._create_workflow()
        self.compiled_graph = self.workflow.compile()
    
    def _create_prompt(self):
        """Create the agent prompt template with memory context"""
        
        def prompt(state):
            # Get user_id from state or use default
            config = state.get("config", {})
            configurable = config.get("configurable", {})
            user_id = configurable.get("user_id", "default_user")
            
            # Search over memories based on the messages
            store = self.memory_manager.get_store()
            namespace = ("agent_memories", user_id)
            items = store.search(namespace, query=state["messages"][-1].content)
            memories = "\n\n".join(str(item.value) for item in items)
            
            system_msg = {"role": "system", "content": f"## Memories:\n\n{memories}"}
            return [system_msg] + state["messages"]
            
        return prompt
    
    def _create_workflow(self):
        """Create the LangGraph workflow"""
        def should_continue(state: FloorPlanState) -> str:
            return "action" if state["messages"][-1].tool_calls else END

        def call_agent(state: FloorPlanState):
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
            
            # Get user_id from config for memory operations
            config = state.get("config", {})
            configurable = config.get("configurable", {})
            user_id = configurable.get("user_id", "default_user")
            
            # Set up configuration with user_id for memory tools
            agent_config = {
                "configurable": {
                    "user_id": user_id
                }
            }
            
            # Invoke the agent executor with the updated state and config
            response = self.agent_executor.invoke(
                state_with_context,
                config=agent_config
            )
            
            return {"messages": [AIMessage(content=response["messages"][-1].content)]}

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