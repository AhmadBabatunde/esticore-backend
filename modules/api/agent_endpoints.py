"""
Unified agent API endpoints for the Floor Plan Agent API
"""
import os
import uuid
import re
import json
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from langchain_core.messages import HumanMessage

from modules.config.settings import settings
from modules.config.utils import load_registry, delete_file_after_delay
from modules.database import db_manager
from modules.agent import agent_workflow
from modules.projects.service import project_service

def extract_manual_suggestions(text: str) -> list:
    """Extract manually formatted suggestions from the response text."""
    suggestions = []
    
    # Look for numbered list items with patterns like:
    # 1. **Title** (Page X): Description
    # or 1. **Title** (Page X) - Description
    pattern = r'(\d+)\. \*\*([^*]+)\*\* \(Page (\d+)\)[:\-] ([^\n]+)'
    
    matches = re.findall(pattern, text, re.MULTILINE | re.IGNORECASE)
    
    for match in matches:
        number, title, page, description = match
        try:
            suggestions.append({
                "title": title.strip(),
                "page": int(page),
                "description": description.strip()
            })
        except ValueError:
            continue  # Skip if page number is not valid
    
    print(f"DEBUG: Extracted {len(suggestions)} manual suggestions from text")
    return suggestions

router = APIRouter(prefix="/agent", tags=["agent"])

@router.post("/unified")
async def unified_agent(
    background_tasks: BackgroundTasks,
    doc_id: str = Form(...),
    user_instruction: str = Form(...),
    user_id: int = Form(...),
    session_id: str = Form(None)
):
    """
    Single unified endpoint that intelligently handles both chat and annotation workflows.
    The agent automatically determines intent and extracts page information from the instruction.
    """
    # Verify document exists
    reg = load_registry()
    if doc_id not in reg:
        raise HTTPException(404, detail="Document not found")
    
    pdf_path = reg[doc_id]["pdf_path"]
    
    # Extract page number from instruction or default to 1
    page_number = 1
    page_match = re.search(r'page\s+(\d+)', user_instruction.lower())
    if page_match:
        page_number = int(page_match.group(1))
    
    # Get or create session for continuity
    session_id = agent_workflow.get_or_create_chat_session(session_id)
    
    # Add user message to chat history
    agent_workflow.add_chat_message(session_id, "user", user_instruction)
    db_manager.add_chat_message(user_id, session_id, "user", user_instruction)
    
    # Generate unique output path for potential annotations
    output_filename = f"{doc_id}_page_{page_number}_{uuid.uuid4().hex[:8]}_unified.pdf"
    output_pdf_path = os.path.join(settings.OUTPUT_DIR, output_filename)
    
    # Ensure output directory exists
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    
    # Get recent chat context
    chat_history = agent_workflow.get_chat_history(session_id)
    recent_context = ""
    if len(chat_history) > 2:  # If there's previous conversation (more than current message)
        recent_messages = chat_history[-6:-1]  # Last few exchanges, excluding current
        recent_context = "\n\nRecent conversation context:\n"
        for msg in recent_messages:
            recent_context += f"{msg['role']}: {msg['content']}\n"
    
    # Enhanced instruction for the agent
    enhanced_instruction = f"""
Document ID: {doc_id}
User Request: {user_instruction}
Extracted Page: {page_number}{recent_context}

Instructions for AI Agent:
1. Analyze the user's request to determine their intent
2. Extract page number from the instruction if mentioned, otherwise use page {page_number}
3. If they are asking a QUESTION about the document content:
   - ALWAYS use answer_question_with_suggestions (not answer_question_using_rag)
   - This function returns structured JSON with answer and suggestions array
   - Do NOT format suggestions manually in text - let the function handle it
4. If they want to ANNOTATE/HIGHLIGHT/MARK something, follow the annotation workflow:
   - Load PDF
   - Convert page to image  
   - Detect objects
   - Apply requested annotation
   - Save annotated PDF
5. Consider conversation context and respond conversationally
6. Be helpful and provide detailed responses

IMPORTANT: For questions, use answer_question_with_suggestions and return its JSON output directly.

Please proceed based on the user's intent.
"""
    
    initial_state = {
        "messages": [HumanMessage(content=enhanced_instruction)],
        "pdf_path": pdf_path,
        "page_number": page_number,
        "output_path": output_pdf_path,
    }
    
    try:
        print(f"DEBUG: Starting unified agent for doc {doc_id} with instruction: {user_instruction}")
        final_state = agent_workflow.process_request(initial_state)
        final_msg = final_state["messages"][-1].content
        
        # Save assistant response to chat history
        agent_workflow.add_chat_message(session_id, "assistant", final_msg)
        db_manager.add_chat_message(user_id, session_id, "assistant", final_msg)
        
        # Check if annotation was performed (PDF file created)
        if os.path.exists(output_pdf_path):
            print(f"DEBUG: Annotation completed. PDF file created at: {output_pdf_path}")
            
            # Add cleanup task
            background_tasks.add_task(delete_file_after_delay, output_pdf_path, settings.CHAT_FILE_DELETE_DELAY)
            
            # Return the PDF file directly as download with text response in headers
            return FileResponse(
                path=output_pdf_path,
                filename=output_filename,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={output_filename}",
                    "X-Agent-Response": final_msg.replace('\n', ' ').replace('\r', '')[:500],  # Truncate to avoid header size limits
                    "X-Session-ID": session_id,
                    "X-Doc-ID": doc_id,
                    "X-Page-Number": str(page_number)
                }
            )
        else:
            print(f"DEBUG: No annotation file created. Returning information response.")
            
            # Try to parse the response for suggestions
            suggestions = []
            answer_text = final_msg
            
            # Check if the response contains JSON from answer_question_with_suggestions
            try:
                # Look for JSON pattern in the response - try multiple patterns
                json_patterns = [
                    r'\{.*"answer".*"suggestions".*\}',  # Full JSON object
                    r'\{[^}]*"answer"[^}]*"suggestions"[^}]*\}',  # More specific pattern
                ]
                
                parsed_response = None
                
                for pattern in json_patterns:
                    json_match = re.search(pattern, final_msg, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        try:
                            parsed_response = json.loads(json_str)
                            break
                        except json.JSONDecodeError:
                            continue
                
                # If we found a valid JSON response, extract the data
                if parsed_response and isinstance(parsed_response, dict):
                    if "answer" in parsed_response:
                        answer_text = parsed_response["answer"]
                        suggestions = parsed_response.get("suggestions", [])
                        
                        # Ensure suggestions is always a list
                        if not isinstance(suggestions, list):
                            suggestions = []
                            
                        print(f"DEBUG: Extracted {len(suggestions)} suggestions from JSON response")
                    else:
                        print("DEBUG: JSON found but no 'answer' key")
                else:
                    print("DEBUG: No valid JSON response found, attempting to parse manual suggestions from text")
                    
                    # If no JSON found, try to extract manually formatted suggestions from the text
                    suggestions = extract_manual_suggestions(final_msg)
                    
                    # If we found manual suggestions, clean up the answer text
                    if suggestions:
                        # Remove the suggestions section from the answer text
                        # Look for patterns like "Here are some related topics:"
                        split_patterns = [
                            r'\n\nHere are some related topics.*',
                            r'\n\nRelated topics.*',
                            r'\n\n\d+\. \*\*.*',
                            r'\n\nIf you have any specific questions.*'
                        ]
                        
                        for pattern in split_patterns:
                            match = re.search(pattern, answer_text, re.DOTALL | re.IGNORECASE)
                            if match:
                                answer_text = answer_text[:match.start()].strip()
                                break
                    
            except Exception as e:
                print(f"DEBUG: Error parsing response: {e}")
                # If parsing fails, treat the entire response as the answer
                pass
            
            # For RAG/information requests, return JSON response with suggestions
            response_content = {
                "response": answer_text,
                "session_id": session_id,
                "doc_id": doc_id,
                "page": page_number,
                "type": "information",
                "suggestions": suggestions  # Always include suggestions array (empty if none)
            }
            
            return JSONResponse(content=response_content)
            
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        print(f"DEBUG: Exception occurred in unified agent: {str(e)}")
        
        # Save error to chat history
        agent_workflow.add_chat_message(session_id, "assistant", error_msg)
        db_manager.add_chat_message(user_id, session_id, "assistant", error_msg)
        
        return JSONResponse(
            content={
                "response": error_msg,
                "session_id": session_id,
                "doc_id": doc_id,
                "type": "error"
            },
            status_code=500
        )

@router.get("/chat/history")
async def get_chat_history(user_id: int, session_id: str = None, limit: int = 50):
    """
    Retrieve chat history for a specific user.
    If session_id is provided, returns only that session's history.
    Otherwise, returns all chat history for the user.
    """
    try:
        history = db_manager.get_chat_history(user_id, session_id, limit)
        
        # Format the response
        formatted_history = []
        for msg in history:
            formatted_history.append({
                "id": msg.id,
                "session_id": msg.session_id,
                "role": msg.role,
                "message": msg.message,
                "timestamp": msg.timestamp
            })
        
        return {"history": formatted_history}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/chat/sessions")
async def get_user_sessions(user_id: int):
    """
    Get all unique session IDs for a user.
    """
    try:
        sessions = db_manager.get_user_sessions(user_id)
        return {"sessions": sessions}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/project/{project_id}/unified")
async def unified_agent_for_project(
    background_tasks: BackgroundTasks,
    project_id: str,
    user_instruction: str = Form(...),
    user_id: int = Form(...),
    session_id: str = Form(None)
):
    """
    Project-aware unified endpoint that works with project context.
    Automatically extracts the document from the project and provides project context.
    """
    # Validate project access
    if not project_service.validate_project_access(project_id, user_id):
        raise HTTPException(403, detail="Access denied or project not found")
    
    # Get project information
    project = project_service.get_project(project_id)
    if not project or not project.get("document"):
        raise HTTPException(400, detail="Project has no associated document")
    
    doc_id = project["document"]["doc_id"]
    
    # Verify document exists in registry
    reg = load_registry()
    if doc_id not in reg:
        raise HTTPException(404, detail="Document not found")
    
    pdf_path = reg[doc_id]["pdf_path"]
    
    # Extract page number from instruction or default to 1
    page_number = 1
    page_match = re.search(r'page\s+(\d+)', user_instruction.lower())
    if page_match:
        page_number = int(page_match.group(1))
    
    # Get or create session for continuity
    session_id = agent_workflow.get_or_create_chat_session(session_id)
    
    # Add user message to chat history
    agent_workflow.add_chat_message(session_id, "user", user_instruction)
    db_manager.add_chat_message(user_id, session_id, "user", user_instruction)
    
    # Generate unique output path for potential annotations
    output_filename = f"{project_id}_{doc_id}_page_{page_number}_{uuid.uuid4().hex[:8]}_project.pdf"
    output_pdf_path = os.path.join(settings.OUTPUT_DIR, output_filename)
    
    # Ensure output directory exists
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    
    # Get recent chat context
    chat_history = agent_workflow.get_chat_history(session_id)
    recent_context = ""
    if len(chat_history) > 2:  # If there's previous conversation (more than current message)
        recent_messages = chat_history[-6:-1]  # Last few exchanges, excluding current
        recent_context = "\n\nRecent conversation context:\n"
        for msg in recent_messages:
            recent_context += f"{msg['role']}: {msg['content']}\n"
    
    # Enhanced instruction for the agent with project context
    enhanced_instruction = f"""
Project Context:
- Project ID: {project_id}
- Project Name: {project["name"]}
- Project Description: {project["description"]}
- Document ID: {doc_id}
- Document: {project["document"]["filename"]} ({project["document"]["pages"]} pages)

User Request: {user_instruction}
Extracted Page: {page_number}{recent_context}

Instructions for AI Agent:
1. You are working within the context of project "{project["name"]}"
2. Analyze the user's request to determine their intent
3. Extract page number from the instruction if mentioned, otherwise use page {page_number}
4. If they are asking a QUESTION about the document content:
   - ALWAYS use answer_question_with_suggestions (not answer_question_using_rag)
   - This function returns structured JSON with answer and suggestions array
   - Do NOT format suggestions manually in text - let the function handle it
5. If they want to ANNOTATE/HIGHLIGHT/MARK something, follow the annotation workflow:
   - Load PDF
   - Convert page to image  
   - Detect objects
   - Apply requested annotation
   - Save annotated PDF
6. Consider project context and conversation history
7. Be helpful and provide detailed responses

IMPORTANT: For questions, use answer_question_with_suggestions and return its JSON output directly.

Please proceed based on the user's intent.
"""
    
    initial_state = {
        "messages": [HumanMessage(content=enhanced_instruction)],
        "pdf_path": pdf_path,
        "page_number": page_number,
        "output_path": output_pdf_path,
    }
    
    try:
        print(f"DEBUG: Starting project agent for project {project_id} with instruction: {user_instruction}")
        final_state = agent_workflow.process_request(initial_state)
        final_msg = final_state["messages"][-1].content
        
        # Save assistant response to chat history
        agent_workflow.add_chat_message(session_id, "assistant", final_msg)
        db_manager.add_chat_message(user_id, session_id, "assistant", final_msg)
        
        # Check if annotation was performed (PDF file created)
        if os.path.exists(output_pdf_path):
            print(f"DEBUG: Annotation completed. PDF file created at: {output_pdf_path}")
            
            # Add cleanup task
            background_tasks.add_task(delete_file_after_delay, output_pdf_path, settings.CHAT_FILE_DELETE_DELAY)
            
            # Return the PDF file directly as download
            return FileResponse(
                path=output_pdf_path,
                filename=output_filename,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={output_filename}"
                }
            )
        else:
            print(f"DEBUG: No annotation file created. Returning information response.")
            
            # Try to parse the response for suggestions (same logic as unified endpoint)
            suggestions = []
            answer_text = final_msg
            
            # Check if the response contains JSON from answer_question_with_suggestions
            try:
                # Look for JSON pattern in the response - try multiple patterns
                json_patterns = [
                    r'\{.*"answer".*"suggestions".*\}',  # Full JSON object
                    r'\{[^}]*"answer"[^}]*"suggestions"[^}]*\}',  # More specific pattern
                ]
                
                parsed_response = None
                
                for pattern in json_patterns:
                    json_match = re.search(pattern, final_msg, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        try:
                            parsed_response = json.loads(json_str)
                            break
                        except json.JSONDecodeError:
                            continue
                
                # If we found a valid JSON response, extract the data
                if parsed_response and isinstance(parsed_response, dict):
                    if "answer" in parsed_response:
                        answer_text = parsed_response["answer"]
                        suggestions = parsed_response.get("suggestions", [])
                        
                        # Ensure suggestions is always a list
                        if not isinstance(suggestions, list):
                            suggestions = []
                            
                        print(f"DEBUG: Extracted {len(suggestions)} suggestions from JSON response")
                    else:
                        print("DEBUG: JSON found but no 'answer' key")
                else:
                    print("DEBUG: No valid JSON response found, attempting to parse manual suggestions from text")
                    
                    # If no JSON found, try to extract manually formatted suggestions from the text
                    suggestions = extract_manual_suggestions(final_msg)
                    
                    # If we found manual suggestions, clean up the answer text
                    if suggestions:
                        # Remove the suggestions section from the answer text
                        # Look for patterns like "Here are some related topics:"
                        split_patterns = [
                            r'\n\nHere are some related topics.*',
                            r'\n\nRelated topics.*',
                            r'\n\n\d+\. \*\*.*',
                            r'\n\nIf you have any specific questions.*'
                        ]
                        
                        for pattern in split_patterns:
                            match = re.search(pattern, answer_text, re.DOTALL | re.IGNORECASE)
                            if match:
                                answer_text = answer_text[:match.start()].strip()
                                break
                    
            except Exception as e:
                print(f"DEBUG: Error parsing response: {e}")
                # If parsing fails, treat the entire response as the answer
                pass
            
            # For RAG/information requests, return JSON response with suggestions and project context
            response_content = {
                "response": answer_text,
                "session_id": session_id,
                "project_id": project_id,
                "doc_id": doc_id,
                "page": page_number,
                "type": "information",
                "suggestions": suggestions,  # Always include suggestions array (empty if none)
                "project_context": {
                    "name": project["name"],
                    "description": project["description"]
                }
            }
            
            return JSONResponse(content=response_content)
            
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        print(f"DEBUG: Exception occurred in project agent: {str(e)}")
        
        # Save error to chat history
        agent_workflow.add_chat_message(session_id, "assistant", error_msg)
        db_manager.add_chat_message(user_id, session_id, "assistant", error_msg)
        
        return JSONResponse(
            content={
                "response": error_msg,
                "session_id": session_id,
                "project_id": project_id,
                "type": "error"
            },
            status_code=500
        )

