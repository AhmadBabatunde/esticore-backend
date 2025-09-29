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
from modules.agent.tools import (
    load_pdf_for_floorplan,
    convert_pdf_page_to_image,
    detect_floor_plan_objects,
    verify_detections,
    internet_search,
    apply_highlight_annotation,
    apply_circle_annotation,
    apply_rectangle_annotation,
    apply_count_annotation,
    apply_arrow_annotation,
    save_annotated_image_as_pdf_page,
    answer_question_using_rag,
    answer_question_with_suggestions,
    quick_page_analysis,
    analyze_pdf_page_multimodal,
    measure_objects,
    calibrate_scale,
    analyze_object_proportions
)

# List of all available tools
ALL_TOOLS = [
    load_pdf_for_floorplan,
    convert_pdf_page_to_image,
    detect_floor_plan_objects,
    verify_detections,
    internet_search,
    apply_highlight_annotation,
    apply_circle_annotation,
    apply_rectangle_annotation,
    apply_count_annotation,
    apply_arrow_annotation,
    save_annotated_image_as_pdf_page,
    answer_question_using_rag,
    answer_question_with_suggestions,
    quick_page_analysis,
    analyze_pdf_page_multimodal,
    measure_objects,
    calibrate_scale,
    analyze_object_proportions
]
from modules.session import session_manager, context_resolver
from modules.database.models import db_manager

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
# Enhanced Session Management
# ==============================

@dataclass
class ChatMessage:
    """Chat message data structure (kept for backward compatibility)"""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

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
    """Agent workflow using LangGraph with proper tool calling"""
    
    def __init__(self):
        self.memory = SimpleMemory()
        self.session_manager = session_manager
        self.context_resolver = context_resolver
        
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        self.agent = create_tool_calling_agent(self.llm, ALL_TOOLS, self._create_prompt())
        self.agent_executor = AgentExecutor(agent=self.agent, tools=ALL_TOOLS, verbose=True)
        
        # Initialize LangGraph workflow
        self.workflow = self._create_workflow()
        self.compiled_graph = self.workflow.compile()
    
    def _create_prompt(self):
        """Create the agent prompt template"""
        return ChatPromptTemplate.from_messages([
            ("system", """
You are an expert Civil Engineering AI assistant for working with floor plan documents. Your role is to analyze user requests and select the SINGLE most appropriate tool to handle each request.

**TOOL SELECTION GUIDELINES:**

1. **MEASUREMENT REQUESTS** - Use detection + measurement (NO ANNOTATION):
   - "measure [object]", "how wide/tall", "what size", "dimensions of" → detect_floor_plan_objects → measure_objects
   - "how big is", "size of [object]", "width of", "height of" → detect_floor_plan_objects → measure_objects
   - "calibrate scale", "set reference" → calibrate_scale
   - "analyze proportions", "aspect ratio" → analyze_object_proportions

2. **DETECTION REQUESTS** - Use detection tools only:
   - "what objects are on this page", "detect objects", "find [objects]" → detect_floor_plan_objects
   - "verify [objects] exist", "check for [objects]" → verify_detections

3. **DOCUMENT QUESTIONS** - Use ONE question answering tool:
   - General questions → answer_question_with_suggestions
   - Simple factual questions → answer_question_using_rag
   - Specific page analysis → quick_page_analysis

4. **VISUAL/IMAGE ANALYSIS** - Use image tools:
   - "describe this page/layout" → analyze_pdf_page_multimodal (PREFERRED for detailed visual analysis)
   - Basic page conversion → convert_pdf_page_to_image

5. **MULTIMODAL ANALYSIS** - Use analyze_pdf_page_multimodal for:
   - Detailed layout descriptions
   - Spatial relationships analysis
   - Comprehensive visual understanding
   - Combined text and image analysis

6. **EXTERNAL INFORMATION** - Use search:
   - Current info/regulations → internet_search

7. **FILE OPERATIONS** - Use file tools:
   - Load PDF → load_pdf_for_floorplan
   - Save annotated PDF → save_annotated_image_as_pdf_page

**CRITICAL RULES FOR RESPONSE FORMATTING:**
- NEVER include download URLs or file paths in responses
- NEVER use markdown links like [here](file://path) or [Download](path)
- For annotation completions, simply state: "Annotation completed successfully"
- For measurement results, provide the numerical values and units clearly
- For analysis results, provide the findings in clear text
- Keep responses clean and professional without technical file paths

**CRITICAL RULES FOR MEASUREMENT:**
- For measurement requests: ONLY use detect_floor_plan_objects → measure_objects
- NEVER use annotation tools (highlight, circle, rectangle, count, arrow) for measurement requests
- Measurement workflow: detect → measure → return results (no annotation)
- If objects are already detected, use measure_objects directly with existing object data

**MEASUREMENT WORKFLOW:**
1. Use detect_floor_plan_objects to get object detection data
2. Use measure_objects with the detected objects JSON
3. Return measurement results without any annotation

**CRITICAL RULES:**
- Select ONLY ONE tool per user request
- Choose the tool that most directly addresses the user's need
- For measurement: detect + measure only, NO ANNOTATION
- For visual/spatial/layout questions, PREFER analyze_pdf_page_multimodal
- Do not chain multiple tools unless absolutely necessary for measurement
- For complex requests, pick the most relevant primary tool

**RESPONSE FORMAT EXAMPLES:**
✅ CORRECT:
- "The steel base plate measures 450mm in width and 450mm in height."
- "Annotation completed successfully. The doors have been highlighted."
- "I detected 3 windows and 2 doors on this page."
- "The room layout shows a 5m x 4m living area with two bedrooms."

❌ INCORRECT:
- "You can download it [here](C:\\Users\\...\\file.pdf)."
- "Download the annotated file [Download](path/to/file)"
- "File saved at: C:\\temp\\file.pdf"

**TOOL USAGE EXAMPLES:**
- "Measure the width of the steel base plate" → detect_floor_plan_objects → measure_objects
- "How wide is the door?" → detect_floor_plan_objects → measure_objects
- "What are the dimensions of the window?" → detect_floor_plan_objects → measure_objects
- "What objects are on this page?" → detect_floor_plan_objects
- "Verify if there are any steel base plates" → verify_detections
- "What's on page 3?" → quick_page_analysis  
- "Describe the layout of page 2" → analyze_pdf_page_multimodal (PREFERRED)
- "Show me the spatial relationships" → analyze_pdf_page_multimodal
- "Current building codes" → internet_search
- "Explain this floor plan visually" → analyze_pdf_page_multimodal
- "Calibrate the scale using this 2m wall" → calibrate_scale
- "Analyze the proportions of the rooms" → analyze_object_proportions

**MEASUREMENT-SPECIFIC NOTES:**
- The measure_objects tool can automatically detect scale using standard object sizes
- For precise measurements, provide reference_scale parameter if known
- Steel base plates typically measure 150-600mm in width/height
- Standard doors are 900mm wide, windows are 1200mm wide
- The tool provides engineering context for different object types
- Measurements are based on detection only - no visual annotations are applied

Always provide clean, professional responses without file paths or download links.
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
            # Enhanced intent detection for generalization
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

            # Route to correct tool chain
            # All routes use the compiled graph, but intent is passed in context for agent prompt
            final_state = self.compiled_graph.invoke(initial_state, {"recursion_limit": settings.RECURSION_LIMIT, "intent": intent})
            return final_state
        except Exception as e:
            raise Exception(f"Agent workflow error: {str(e)}")
    
    def get_or_create_chat_session(self, session_id: str = None, user_id: int = None, context_type: str = 'GENERAL', context_id: str = None) -> str:
        """Get or create a chat session with context support"""
        # Trigger cleanup occasionally
        if random.random() < settings.SESSION_ACTIVITY_UPDATE_PROBABILITY:
            self.session_manager.cleanup_expired_sessions()
        
        if session_id:
            # Validate existing session
            session = self.session_manager.get_session_by_id(session_id)
            if session and session.is_active:
                # Update activity and return existing session
                self.session_manager.update_session_activity(session_id)
                return session_id
        
        # Create new session if user_id is provided
        if user_id is not None:
            return self.session_manager.get_or_create_session(user_id, context_type, context_id)
        
        # Fallback: create a simple UUID for backward compatibility
        return str(uuid.uuid4())
    
    def get_or_create_context_session(self, user_id: int, context_data: Dict[str, Any]) -> str:
        """Get or create a session based on context data"""
        context_type, context_id = self.context_resolver.resolve_context(context_data)
        return self.session_manager.get_or_create_session(user_id, context_type, context_id)
    
    def add_chat_message(self, session_id: str, role: str, content: str, user_id: int = None):
        """Add a message to chat session with enhanced context support"""
        if user_id is not None:
            # Use the new session manager to add message with context
            success = self.session_manager.add_message_to_session(session_id, user_id, role, content)
            if not success:
                print(f"Warning: Failed to add message to session {session_id}")
        else:
            # Fallback to old memory system for backward compatibility
            if hasattr(self, 'chat_sessions'):
                self.chat_sessions.add_message(session_id, role, content)
    
    def get_chat_history(self, session_id: str, user_id: int = None, limit: int = 50) -> List[Dict]:
        """Get chat history for a session"""
        if user_id is not None:
            # Use database-backed history
            messages = db_manager.get_chat_history(user_id, session_id, limit)
            # Convert to the expected format
            return [
                {
                    "role": msg.role,
                    "content": msg.message,
                    "timestamp": msg.timestamp
                }
                for msg in reversed(messages)  # Reverse to get chronological order
            ]
        else:
            # Fallback to old memory system for backward compatibility
            if hasattr(self, 'chat_sessions'):
                return self.chat_sessions.get_messages(session_id)
            return []
    
    def get_session_context(self, session_id: str) -> tuple:
        """Get the context type and ID for a session"""
        return self.session_manager.get_session_context(session_id)
    
    def validate_session_access(self, session_id: str, user_id: int) -> bool:
        """Validate that a user has access to a session"""
        return self.session_manager.validate_session_access(session_id, user_id)

# Global agent workflow instance
agent_workflow = AgentWorkflow()