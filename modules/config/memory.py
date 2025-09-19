from langgraph.store.memory import InMemoryStore
from langmem import create_manage_memory_tool, create_search_memory_tool

class MemoryManager:
    """
    Manages long-term memory for the agent using LangMem and LangGraph store.
    Provides tools for creating, updating, searching and deleting memories.
    """
    
    def __init__(self):
        # Initialize the memory store with embedding configuration
        self.store = InMemoryStore(
            index={
                "dims": 1536,
                "embed": "openai:text-embedding-3-small"
            }
        )
        
        # Create memory tools that will be used by the agent
        self.manage_memory_tool = create_manage_memory_tool(namespace=("agent_memories", "{user_id}"))
        self.search_memory_tool = create_search_memory_tool(namespace=("agent_memories", "{user_id}"))
        
        # List of memory tools to be registered with the agent
        self.memory_tools = [
            self.manage_memory_tool,
            self.search_memory_tool
        ]
    
    def get_memory_tools(self):
        """Return the list of memory tools for the agent"""
        return self.memory_tools
    
    def get_store(self):
        """Return the memory store instance"""
        return self.store