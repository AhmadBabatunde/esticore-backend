"""
Agent tools for floor plan processing and annotation
"""
import os
import json
import uuid
import tempfile
import tiktoken
from typing import List, Dict, Tuple
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from inference_sdk import InferenceHTTPClient
from langchain_tavily import TavilySearch

from modules.config.settings import settings
from modules.pdf_processing.service import pdf_processor

# Initialize Roboflow client
CLIENT = InferenceHTTPClient(
    api_url=settings.ROBOFLOW_API_URL,
    api_key=settings.ROBOFLOW_API_KEY
)

# Initialize tokenizer for chunking
tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")

def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string."""
    return len(tokenizer.encode(text))

def chunk_context_for_processing(context: str, question: str, max_chunk_tokens: int = 4000) -> List[Dict[str, str]]:
    """Split large context into manageable chunks for processing."""
    # Reserve tokens for question, prompt template, and response
    system_overhead = estimate_tokens(f"""Based on the following context from the document, answer the user's question.
    
    Context:
    
    User question: {question}
    
    Provide a helpful and accurate answer:""")
    
    available_tokens = max_chunk_tokens - system_overhead - 500  # 500 tokens buffer for response
    
    if estimate_tokens(context) <= available_tokens:
        return [{"chunk": context, "chunk_id": 1, "total_chunks": 1}]
    
    # Split context into smaller pieces
    lines = context.split('\n\n')
    chunks = []
    current_chunk = ""
    chunk_id = 1
    
    for line in lines:
        test_chunk = current_chunk + "\n\n" + line if current_chunk else line
        
        if estimate_tokens(test_chunk) <= available_tokens:
            current_chunk = test_chunk
        else:
            if current_chunk:
                chunks.append({
                    "chunk": current_chunk,
                    "chunk_id": chunk_id,
                    "total_chunks": 0  # Will be updated later
                })
                chunk_id += 1
                current_chunk = line
            else:
                # Single line is too long, need to split it further
                words = line.split(' ')
                temp_chunk = ""
                for word in words:
                    test_word_chunk = temp_chunk + " " + word if temp_chunk else word
                    if estimate_tokens(test_word_chunk) <= available_tokens:
                        temp_chunk = test_word_chunk
                    else:
                        if temp_chunk:
                            chunks.append({
                                "chunk": temp_chunk,
                                "chunk_id": chunk_id,
                                "total_chunks": 0
                            })
                            chunk_id += 1
                            temp_chunk = word
                        else:
                            # Single word is too long, truncate it
                            temp_chunk = word[:available_tokens//2]
                            chunks.append({
                                "chunk": temp_chunk,
                                "chunk_id": chunk_id,
                                "total_chunks": 0
                            })
                            chunk_id += 1
                            temp_chunk = ""
                
                if temp_chunk:
                    current_chunk = temp_chunk
    
    if current_chunk:
        chunks.append({
            "chunk": current_chunk,
            "chunk_id": chunk_id,
            "total_chunks": 0
        })
    
    # Update total_chunks count
    total_chunks = len(chunks)
    for chunk in chunks:
        chunk["total_chunks"] = total_chunks
    
    return chunks

def combine_chunk_responses(responses: List[str], question: str) -> str:
    """Combine responses from multiple chunks into a coherent answer."""
    if len(responses) == 1:
        return responses[0]
    
    # Combine all responses
    combined_text = "\n\n".join([f"Section {i+1}: {resp}" for i, resp in enumerate(responses)])
    
    # Use LLM to synthesize the combined responses
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
    synthesis_prompt = f"""I have gathered information from multiple sections of a document to answer this question: {question}

Combined information from all sections:
{combined_text}

Please provide a comprehensive, coherent answer that synthesizes the information from all sections. Remove any redundancy and organize the information logically:"""
    
    try:
        synthesis_response = llm.invoke(synthesis_prompt)
        return synthesis_response.content
    except Exception as e:
        print(f"DEBUG: Error in synthesis, returning combined text: {e}")
        return f"Based on the document analysis:\n\n" + "\n\n".join(responses)

def get_internet_search_results(query: str, max_results: int = 3) -> str:
    """Get internet search results for supplementary information."""
    try:
        # Initialize Tavily search tool with configuration from settings
        tavily_search = TavilySearch(
            max_results=max_results,
            topic="general",
            include_answer=True,
            include_raw_content=False,
            include_images=False
        )
        
        # Execute the search
        result = tavily_search.invoke({"query": query})
        
        # Format the results for inclusion in answers
        search_results = result.get("results", [])
        if not search_results:
            return ""
        
        formatted_results = "Additional context from current information:\n"
        for i, item in enumerate(search_results[:max_results], 1):
            title = item.get("title", "No title")
            content = item.get("content", "No content")
            url = item.get("url", "")
            
            formatted_results += f"\n{i}. {title}\n"
            formatted_results += f"   {content[:300]}..." if len(content) > 300 else f"   {content}"
            if url:
                formatted_results += f"\n   Source: {url}"
            formatted_results += "\n"
        
        return formatted_results
        
    except Exception as e:
        print(f"DEBUG: Internet search failed: {e}")
        return ""

def create_comprehensive_answer(doc_content: str, web_content: str, question: str, citations: List = None) -> str:
    """Create a comprehensive answer combining document content and web information."""
    try:
        # Prepare the content for the LLM
        combined_context = ""
        
        if doc_content:
            combined_context += f"DOCUMENT INFORMATION:\n{doc_content}\n\n"
        
        if web_content:
            combined_context += f"CURRENT INFORMATION:\n{web_content}\n\n"
        
        # If no content from either source, provide a helpful response
        if not combined_context.strip():
            return f"I understand you're asking about: {question}. Let me provide what I can tell you about this topic based on general knowledge and analysis capabilities. I can analyze both textual content and visual elements (layouts, diagrams, spatial relationships) when available. However, I recommend consulting current resources, expert documentation, and specialized sources for the most accurate and up-to-date information."
        
        # Create citation references if available
        citation_text = ""
        if citations:
            citation_text = "\n\nDocument citations:\n"
            for citation in citations[:5]:
                citation_text += f"[{citation['id']}] Page {citation['page']}\n"
        
        # Use LLM to create comprehensive answer
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        comprehensive_prompt = f"""Based on the following information sources, provide a comprehensive and detailed answer to the user's question. Synthesize information from both the document content (including any visual analysis) and current web sources to give the most complete response possible.

QUESTION: {question}

AVAILABLE INFORMATION:
{combined_context}

Please provide a thorough, well-organized answer that:
1. Directly addresses the question
2. Combines relevant information from all sources (document text, visual analysis, and web content)
3. Provides specific details and examples where available
4. Offers practical insights and recommendations
5. Integrates visual information (layouts, designs, spatial relationships) when relevant
6. Maintains accuracy while being comprehensive

If some aspects of the question cannot be fully answered from the available sources, acknowledge this but still provide all relevant information that is available.{citation_text}"""
        
        response = llm.invoke(comprehensive_prompt)
        return response.content
        
    except Exception as e:
        print(f"DEBUG: Error creating comprehensive answer: {e}")
        # Fallback to combining the content directly
        fallback_answer = f"Based on the available information regarding '{question}':\n\n"
        if doc_content:
            fallback_answer += f"From the document: {doc_content}\n\n"
        if web_content:
            fallback_answer += f"Current information: {web_content}\n\n"
        return fallback_answer or f"I understand you're asking about {question}. This appears to be an important topic that would benefit from consulting current expert sources and documentation."

def should_use_internet_search(question: str) -> bool:
    """Determine if a question requires internet search based on keywords and context."""
    question_lower = question.lower()
    
    # Greetings and simple interactions - no search needed
    greeting_patterns = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening', 'how are you', 'thanks', 'thank you']
    if any(greeting in question_lower for greeting in greeting_patterns):
        return False
    
    # Keywords that indicate need for current/recent information
    current_info_keywords = [
        'current', 'recent', 'latest', 'new', 'updated', 'today', 'now', 'this year', 
        'market trends', 'news', 'regulations', 'standards', 'prices', 'cost', 
        'what is happening', 'what happened', 'recent developments', 'updates'
    ]
    
    # Keywords that indicate document-based questions
    document_keywords = [
        'page', 'document', 'pdf', 'floor plan', 'drawing', 'diagram', 'layout',
        'what does this show', 'what is on', 'describe', 'analyze', 'explain this'
    ]
    
    # If question contains document-specific keywords, don't search internet
    if any(keyword in question_lower for keyword in document_keywords):
        return False
    
    # If question explicitly asks for current information, search internet
    if any(keyword in question_lower for keyword in current_info_keywords):
        return True
    
    # Default: don't search internet unless explicitly needed
    return False

def process_question_with_hybrid_search(doc_id: str, question: str, include_suggestions: bool = False) -> Dict:
    """Process question using both document RAG and internet search for comprehensive answers with concurrent processing."""
    doc_content = ""
    web_content = ""
    citations = []
    most_referenced_page = None
    suggestions = []
    
    import concurrent.futures
    import threading
    
    # Results containers for concurrent operations
    doc_result = {"content": "", "citations": [], "most_referenced_page": None}
    web_result = {"content": ""}
    
    # Check if internet search is needed
    needs_internet_search = should_use_internet_search(question)
    
    def fetch_document_content():
        """Fetch document content in a separate thread with image analysis support."""
        try:
            print(f"DEBUG: Retrieving document content for: {question}")
            docs = None
            if getattr(pdf_processor, 'use_database_storage', False):
                docs = pdf_processor.query_document_vectors(doc_id, question, k=8)
                # docs is a list of dicts with 'page' and 'text'
            else:
                vs = pdf_processor.load_vectorstore(doc_id)
                docs = vs.similarity_search(question, k=8)
                # docs is a list of objects with .metadata and .page_content

            if docs:
                # Create citations from docs
                doc_citations = []
                for i, doc in enumerate(docs):
                    if isinstance(doc, dict):
                        doc_citations.append({
                            "id": i + 1,
                            "page": doc.get("page", 1),
                            "text": doc.get("text", ""),
                            "relevance_score": 0.8,
                            "doc_id": doc_id
                        })
                    else:
                        doc_citations.append({
                            "id": i + 1,
                            "page": doc.metadata.get("page", 1),
                            "text": doc.page_content,
                            "relevance_score": 0.8,
                            "doc_id": doc_id
                        })
                # Find most referenced page
                page_counts = {}
                for citation in doc_citations:
                    page = citation["page"]
                    page_counts[page] = page_counts.get(page, 0) + 1
                doc_most_referenced = None
                if page_counts:
                    doc_most_referenced = max(page_counts.items(), key=lambda x: x[1])[0]
                
                # Format document content
                context = "\n\n".join([f"Page {d.metadata.get('page', 'N/A')}: {d.page_content}" for d in docs])
                
                # Check if visual analysis is needed for pages with minimal text
                visual_analysis_needed = any(keyword in question.lower() for keyword in [
                    'layout', 'arrangement', 'position', 'where', 'located', 'diagram', 'drawing', 
                    'plan', 'design', 'visual', 'look', 'appearance', 'orientation', 'spatial', 
                    'show', 'see', 'view', 'display', 'illustrate', 'color', 'shape', 'size'
                ])
                
                multimodal_analysis = ""
                if visual_analysis_needed:
                    print(f"DEBUG: Visual question detected, checking pages for image analysis")
                    # Get unique pages from docs
                    relevant_pages = list(set(d.metadata.get('page', 1) for d in docs[:4]))  # Limit to 4 pages for speed
                    
                    try:
                        doc_info = pdf_processor.get_document_info(doc_id)
                        reader = PdfReader(doc_info["pdf_path"])
                        
                        # Check which pages need visual analysis (minimal text)
                        pages_needing_visual = []
                        for page_num in relevant_pages[:2]:  # Limit to 2 pages for speed
                            try:
                                if page_num <= len(reader.pages):
                                    page = reader.pages[page_num - 1]
                                    raw_text = page.extract_text()
                                    if not raw_text or len(raw_text.strip()) < 50 or '[No text extracted:' in raw_text:
                                        pages_needing_visual.append(page_num)
                            except Exception as e:
                                print(f"DEBUG: Error checking page {page_num} for visual analysis: {e}")
                        
                        # Perform visual analysis on pages that need it (max 1 for speed)
                        if pages_needing_visual:
                            print(f"DEBUG: Performing visual analysis on {len(pages_needing_visual[:1])} pages")
                            for page_num in pages_needing_visual[:1]:
                                try:
                                    analysis = analyze_pdf_page_multimodal(doc_id, page_num)
                                    multimodal_analysis += f"\n\nVisual analysis of page {page_num}:\n{analysis}"
                                except Exception as e:
                                    print(f"DEBUG: Error in visual analysis for page {page_num}: {e}")
                                    continue
                    except Exception as e:
                        print(f"DEBUG: Error in visual analysis setup: {e}")
                
                # Combine text and visual content
                enhanced_context = context
                if multimodal_analysis:
                    enhanced_context += f"\n\nAdditional visual insights:{multimodal_analysis}"
                
                # Handle chunking if necessary (smaller chunks for speed)
                chunks = chunk_context_for_processing(enhanced_context, question, max_chunk_tokens=3000)
                
                if len(chunks) == 1:
                    doc_result["content"] = chunks[0]['chunk']
                else:
                    # Process multiple chunks quickly
                    chunk_responses = []
                    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
                    
                    for chunk_info in chunks[:3]:  # Limit to 3 chunks for speed
                        prompt = f"""Extract key information from this document section for: {question}

Section:
{chunk_info['chunk']}

Provide only relevant information (max 2 sentences). If no relevant info, respond "No relevant information.":"""
                        
                        try:
                            chunk_response = llm.invoke(prompt)
                            if "No relevant information" not in chunk_response.content:
                                chunk_responses.append(chunk_response.content)
                        except Exception as e:
                            print(f"DEBUG: Error processing document chunk: {e}")
                            continue
                    
                    if chunk_responses:
                        doc_result["content"] = "\n\n".join(chunk_responses)
                
                doc_result["citations"] = doc_citations
                doc_result["most_referenced_page"] = doc_most_referenced
                
        except Exception as e:
            print(f"DEBUG: Error retrieving document content: {e}")
    
    def fetch_web_content():
        """Fetch web content in a separate thread - only if needed."""
        try:
            if needs_internet_search:
                print(f"DEBUG: Searching internet for: {question}")
                web_result["content"] = get_internet_search_results(question, max_results=2)  # Reduced for speed
            else:
                print(f"DEBUG: Skipping internet search for: {question}")
        except Exception as e:
            print(f"DEBUG: Error fetching web content: {e}")
    
    try:
        # Execute operations - concurrent only if internet search is needed
        if needs_internet_search:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both tasks
                doc_future = executor.submit(fetch_document_content)
                web_future = executor.submit(fetch_web_content)
                
                # Wait for both to complete with timeout for speed
                try:
                    concurrent.futures.wait([doc_future, web_future], timeout=10.0)  # 10 second timeout
                except concurrent.futures.TimeoutError:
                    print("DEBUG: Timeout in concurrent processing, proceeding with available results")
        else:
            # Only fetch document content
            fetch_document_content()
        
        # Extract results
        doc_content = doc_result["content"]
        web_content = web_result["content"]
        citations = doc_result["citations"]
        most_referenced_page = doc_result["most_referenced_page"]
        
        # Generate suggestions quickly if requested
        if include_suggestions and citations:
            relevant_pages = list(set(c["page"] for c in citations[:3]))  # Reduced for speed
            for i, page_num in enumerate(relevant_pages[:2]):  # Max 2 suggestions for speed
                suggestions.append({
                    "title": f"Page {page_num} Details",
                    "page": page_num,
                    "description": f"Additional information on page {page_num}."
                })
        
        # Create comprehensive answer with timeout protection
        try:
            comprehensive_answer = create_comprehensive_answer(doc_content, web_content, question, citations)
        except Exception as e:
            print(f"DEBUG: Error in comprehensive answer generation: {e}")
            # Quick fallback
            comprehensive_answer = f"Based on available information regarding '{question}': "
            if doc_content:
                comprehensive_answer += f"From the document: {doc_content[:500]}... "
            if web_content:
                comprehensive_answer += f"Current information: {web_content[:500]}..."
            if not doc_content and not web_content:
                comprehensive_answer += "This topic requires further research from current expert sources and documentation."
        
        return {
            "answer": comprehensive_answer,
            "suggestions": suggestions,
            "citations": citations,
            "most_referenced_page": most_referenced_page,
            "has_document_content": bool(doc_content),
            "has_web_content": bool(web_content)
        }
        
    except Exception as e:
        print(f"DEBUG: Error in hybrid search processing: {e}")
        # Ultra-fast fallback response
        fallback_answer = f"I understand you're asking about: {question}. This is an important topic. Based on general knowledge and best practices, I can provide that this involves multiple considerations including technical specifications, practical factors, regulatory requirements, and current standards. For the most comprehensive and accurate information, I recommend consulting current expert sources, documentation, and specialized resources relevant to your specific context."
        
        return {
            "answer": fallback_answer,
            "suggestions": [],
            "citations": [],
            "most_referenced_page": None,
            "has_document_content": False,
            "has_web_content": False
        }

@tool
def load_pdf_for_floorplan(pdf_path: str) -> str:
    """Load and validate a PDF file for floor plan processing."""
    try:
        if not os.path.exists(pdf_path):
            return f"Error: PDF file not found at '{pdf_path}'."

        # Try to convert first page to verify PDF is readable
        images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=1)
        if not images:
            return f"Error: Could not read PDF pages from '{pdf_path}'."

        return f"PDF '{pdf_path}' loaded successfully and is ready for floor plan processing."
    except Exception as e:
        return f"Error loading PDF: {str(e)}"

@tool
def convert_pdf_page_to_image(pdf_path: str, page: int = 1, dpi: int = 300) -> str:
    """Convert a specific page of a PDF to a temporary image file for processing."""
    try:
        if not os.path.exists(pdf_path):
            return f"Error: PDF file not found at '{pdf_path}'."

        print(f"DEBUG: Converting PDF page {page} to image with DPI {dpi}")
        images = convert_from_path(pdf_path, dpi=dpi, first_page=page, last_page=page)

        if not images:
            return f"Error: Page {page} not found in PDF."

        temp_image_path = f"temp_floor_plan_page_{page}.png"
        images[0].save(temp_image_path, "PNG")

        print(f"DEBUG: Temporary image saved to {temp_image_path}")
        return json.dumps({"success": True, "image_path": temp_image_path, "page": page})
    except Exception as e:
        return json.dumps({"success": False, "error": f"Error converting PDF to image: {str(e)}"})

@tool
def detect_floor_plan_objects(image_path: str = "temp_floor_plan.png", conf_threshold: float = 0.38) -> str:
    """Detect all objects in the floor plan image using a Roboflow model and return a JSON list of objects."""
    try:
        if not os.path.exists(image_path):
            return f"Error: Image file not found at '{image_path}'."

        print(f"DEBUG: Running Roboflow inference on {image_path}")

        # Run inference
        result = CLIENT.infer(image_path, model_id=settings.ROBOFLOW_MODEL_ID)

        detected_objects = []
        for pred in result.get("predictions", []):
            # Convert from (x_center, y_center, width, height) to (x1, y1, x2, y2)
            x_center, y_center = pred["x"], pred["y"]
            w, h = pred["width"], pred["height"]
            x1, y1 = int(x_center - w / 2), int(y_center - h / 2)
            x2, y2 = int(x_center + w / 2), int(y_center + h / 2)

            obj = {
                "bbox": [x1, y1, x2, y2],
                "class_name": pred["class"],
                "confidence": round(pred["confidence"], 2),
                "class_id": pred["class_id"],
            }
            detected_objects.append(obj)

        print(f"DEBUG: Detected {len(detected_objects)} objects")
        return json.dumps(detected_objects, indent=2)
    except Exception as e:
        return f"Error during detection: {str(e)}"

@tool
def apply_highlight_annotation(image_path: str = "temp_floor_plan.png",
                               objects_json: str = "",
                               filter_condition: str = "") -> str:
    """Apply a semi-transparent highlight over detected objects matching the filter condition."""
    try:
        if not objects_json:
            return "Error: No objects data provided."

        try:
            all_objects = json.loads(objects_json)
            if not isinstance(all_objects, list):
                return "Error: Objects data must be a list of detected objects."
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for objects data."

        if not all_objects:
            return "No objects were detected to annotate."

        # Filter objects if a condition is provided
        if filter_condition:
            objects_to_annotate = [
                obj for obj in all_objects
                if filter_condition.lower() in obj.get('class_name', '').lower()
            ]
            if not objects_to_annotate:
                available_classes = sorted(list(set(obj.get('class_name', 'N/A') for obj in all_objects)))
                return f"No objects found matching filter '{filter_condition}'. Available classes: {available_classes}"
        else:
            objects_to_annotate = all_objects

        print(f"DEBUG: Applying highlight annotation to {len(objects_to_annotate)} objects")

        image = Image.open(image_path).convert("RGBA")
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        highlight_color = (255, 255, 0, 64)  # Yellow with transparency

        for obj in objects_to_annotate:
            bbox = obj['bbox']
            draw.rectangle(bbox, fill=highlight_color)

        image = Image.alpha_composite(image, overlay).convert("RGB")
        image.save(image_path)

        if filter_condition:
            return f"Success: Applied highlight annotation to {len(objects_to_annotate)} objects matching '{filter_condition}'."
        else:
            return f"Success: Applied highlight annotation to all {len(objects_to_annotate)} detected objects."

    except Exception as e:
        return f"Error applying highlight: {str(e)}"

@tool
def apply_circle_annotation(image_path: str = "temp_floor_plan.png", objects_json: str = "", filter_condition: str = "") -> str:
    """Draw circles around the center of detected objects matching the filter condition."""
    try:
        if not objects_json:
            return "Error: No objects data provided."

        try:
            all_objects = json.loads(objects_json)
            if not isinstance(all_objects, list):
                return "Error: Objects data must be a list of detected objects."
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for objects data."

        if not all_objects:
            return "No objects were detected to annotate."

        if filter_condition:
            objects_to_annotate = [
                obj for obj in all_objects
                if filter_condition.lower() in obj.get('class_name', '').lower()
            ]
            if not objects_to_annotate:
                available_classes = sorted(list(set(obj.get('class_name', 'N/A') for obj in all_objects)))
                return f"No objects found matching filter '{filter_condition}'. Available classes: {available_classes}"
        else:
            objects_to_annotate = all_objects

        print(f"DEBUG: Applying circle annotation to {len(objects_to_annotate)} objects")

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        radius = 15
        circle_color = (255, 0, 0)  # Red
        text_color = (0, 0, 0)   # Black text
        
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except:
            font = ImageFont.load_default()

        for obj in objects_to_annotate:
            bbox = obj['bbox']
            class_name = obj.get("class_name", "unknown")
            x1, y1, x2, y2 = bbox
            center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
            
            draw.ellipse(
                [(center_x - radius, center_y - radius), (center_x + radius, center_y + radius)],
                outline=circle_color, width=3
            )
            
            # Add label text above the box
            text_x, text_y = bbox[0], max(0, bbox[1] - 20)
            draw.text((text_x, text_y), class_name, fill=text_color, font=font)

        image.save(image_path)

        if filter_condition:
            return f"Success: Applied circle annotation to {len(objects_to_annotate)} objects matching '{filter_condition}'."
        else:
            return f"Success: Applied circle annotation to all {len(objects_to_annotate)} detected objects."

    except Exception as e:
        return f"Error applying circles: {str(e)}"

@tool
def apply_rectangle_annotation(image_path: str = "temp_floor_plan.png", objects_json: str = "", filter_condition: str = "") -> str:
    """Draw rectangles around detected objects matching the filter condition and label with class name."""
    try:
        if not objects_json:
            return "Error: No objects data provided."

        try:
            all_objects = json.loads(objects_json)
            if not isinstance(all_objects, list):
                return "Error: Objects data must be a list of detected objects."
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for objects data."

        if not all_objects:
            return "No objects were detected to annotate."

        # Filter if requested
        if filter_condition:
            objects_to_annotate = [
                obj for obj in all_objects
                if filter_condition.lower() in obj.get('class_name', '').lower()
            ]
            if not objects_to_annotate:
                available_classes = sorted(list(set(obj.get('class_name', 'N/A') for obj in all_objects)))
                return f"No objects found matching filter '{filter_condition}'. Available classes: {available_classes}"
        else:
            objects_to_annotate = all_objects

        print(f"DEBUG: Applying rectangle+label annotation to {len(objects_to_annotate)} objects")

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        rectangle_color = (0, 0, 255)  # Blue
        text_color = (0, 0, 0)   # Black text

        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except:
            font = ImageFont.load_default()

        for obj in objects_to_annotate:
            bbox = obj['bbox']
            class_name = obj.get("class_name", "unknown")

            # Draw rectangle
            draw.rectangle(bbox, outline=rectangle_color, width=3)

            # Add label text above the box
            text_x, text_y = bbox[0], max(0, bbox[1] - 20)
            draw.text((text_x, text_y), class_name, fill=text_color, font=font)

        image.save(image_path)

        if filter_condition:
            return f"Success: Applied rectangle+label annotation to {len(objects_to_annotate)} objects matching '{filter_condition}'."
        else:
            return f"Success: Applied rectangle+label annotation to all {len(objects_to_annotate)} detected objects."

    except Exception as e:
        return f"Error applying rectangles: {str(e)}"

@tool
def apply_count_annotation(image_path: str = "temp_floor_plan.png", objects_json: str = "", filter_condition: str = "") -> str:
    """Number detected objects matching the filter condition, placing a numbered circle near their bounding box."""
    try:
        if not objects_json:
            return "Error: No objects data provided."

        try:
            all_objects = json.loads(objects_json)
            if not isinstance(all_objects, list):
                return "Error: Objects data must be a list of detected objects."
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for objects data."

        if not all_objects:
            return "No objects were detected to annotate."

        if filter_condition:
            objects_to_annotate = [
                obj for obj in all_objects
                if filter_condition.lower() in obj.get('class_name', '').lower()
            ]
            if not objects_to_annotate:
                available_classes = sorted(list(set(obj.get('class_name', 'N/A') for obj in all_objects)))
                return f"No objects found matching filter '{filter_condition}'. Available classes: {available_classes}"
        else:
            objects_to_annotate = all_objects

        print(f"DEBUG: Applying count annotation to {len(objects_to_annotate)} objects")

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        radius = 15
        count_color = (0, 255, 0)   # Green
        text_color = (0, 0, 0)      # Black for better contrast

        for i, obj in enumerate(objects_to_annotate, 1):
            x1, y1, _, _ = obj['bbox']
            marker_x, marker_y = x1, y1

            draw.ellipse(
                [(marker_x - radius, marker_y - radius), (marker_x + radius, marker_y + radius)],
                fill=count_color
            )

            text = str(i)
            try:
                bbox_text = draw.textbbox((0, 0), text)
                text_width, text_height = bbox_text[2] - bbox_text[0], bbox_text[3] - bbox_text[1]
            except AttributeError:
                text_size = draw.textlength(text)
                text_width, text_height = text_size, text_size

            draw.text(
                (marker_x - text_width / 2, marker_y - text_height / 2),
                text, fill=text_color, align="center"
            )

        image.save(image_path)

        count = len(objects_to_annotate)
        if filter_condition:
            return f"Success: Applied count annotation to {count} objects matching '{filter_condition}' (numbered 1-{count})."
        else:
            return f"Success: Applied count annotation to all {count} detected objects (numbered 1-{count})."

    except Exception as e:
        return f"Error applying count annotation: {str(e)}"

@tool
def apply_arrow_annotation(image_path: str = "temp_floor_plan.png", objects_json: str = "", filter_condition: str = "") -> str:
    """Draw arrows pointing to detected objects matching the filter condition."""
    try:
        if not objects_json:
            return "Error: No objects data provided."

        try:
            all_objects = json.loads(objects_json)
            if not isinstance(all_objects, list):
                return "Error: Objects data must be a list of detected objects."
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for objects data."

        if not all_objects:
            return "No objects were detected to annotate."

        if filter_condition:
            objects_to_annotate = [
                obj for obj in all_objects
                if filter_condition.lower() in obj.get('class_name', '').lower()
            ]
            if not objects_to_annotate:
                available_classes = sorted(list(set(obj.get('class_name', 'N/A') for obj in all_objects)))
                return f"No objects found matching filter '{filter_condition}'. Available classes: {available_classes}"
        else:
            objects_to_annotate = all_objects

        print(f"DEBUG: Applying arrow annotation to {len(objects_to_annotate)} objects")

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        arrow_color = (255, 0, 255)  # Magenta
        text_color = (0, 0, 0)   # Black text

        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except:
            font = ImageFont.load_default()

        for obj in objects_to_annotate:
            bbox = obj['bbox'] 
            x1, y1, _, _ = bbox
            target_x, target_y = x1, y1
            class_name = obj.get("class_name", "unknown")

            # Arrow starts from outside the box and points to the target
            start_x, start_y = target_x - 30, target_y - 30

            draw.line([(start_x, start_y), (target_x, target_y)], fill=arrow_color, width=4)
            # Arrow head
            draw.polygon(
                [(target_x, target_y), (target_x + 12, target_y + 5), (target_x + 5, target_y + 12)],
                fill=arrow_color
            )
            # Add label text above the box
            text_x, text_y = bbox[0], max(0, bbox[1] - 20)
            draw.text((text_x, text_y), class_name, fill=text_color, font=font)

        image.save(image_path)

        if filter_condition:
            return f"Success: Applied arrow annotation to {len(objects_to_annotate)} objects matching '{filter_condition}'."
        else:
            return f"Success: Applied arrow annotation to all {len(objects_to_annotate)} detected objects."

    except Exception as e:
        return f"Error applying arrows: {str(e)}"

@tool
def verify_detections(image_path: str, objects_json: str, requested_object: str) -> str:
    """Verify if the detected objects list contains the requested object type."""
    try:
        if not os.path.exists(image_path):
            return "Error: Image file not found."

        if not objects_json:
            return "Error: No objects data provided to verify."

        try:
            detected_objects = json.loads(objects_json)
            if not isinstance(detected_objects, list):
                return "Error: Objects data must be a list of detected objects."
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for objects data."

        class_counts = {}
        for obj in detected_objects:
            cls = obj.get('class_name', 'unknown').lower()
            class_counts[cls] = class_counts.get(cls, 0) + 1

        response = {
            "requested_object_found": False,
            "class_counts": class_counts,
            "message": "",
            "suggested_filter_condition": ""
        }

        requested_object_lower = requested_object.lower()
        found_classes = []
        
        # Check for exact matches and partial matches
        for cls in class_counts.keys():
            if requested_object_lower == cls:
                # Exact match
                found_classes.append(cls)
                break
            elif requested_object_lower in cls or cls in requested_object_lower:
                # Partial match
                found_classes.append(cls)
        
        if found_classes:
            response['requested_object_found'] = True
            matched_class = found_classes[0]
            count = class_counts[matched_class]
            response['message'] = f"Verification successful: Found {count} objects matching '{requested_object}' (class: '{matched_class}')."
            response['suggested_filter_condition'] = matched_class
        else:
            # No matches found
            response['message'] = f"Verification failed: No objects matching '{requested_object}' were detected. Available classes: {sorted(list(class_counts.keys()))}"
            # Try to suggest the most similar class name
            if class_counts:
                # Find the most similar class name
                import difflib
                closest_matches = difflib.get_close_matches(requested_object_lower, class_counts.keys(), n=3, cutoff=0.3)
                if closest_matches:
                    response['message'] += f"\n\nDid you mean one of these? {closest_matches}"

        return json.dumps(response, indent=2)

    except Exception as e:
        return f"Error verifying detections: {str(e)}"

@tool
def answer_question_using_rag(doc_id: str, question: str) -> str:
    """Answer questions using document content only - simple and fast."""
    try:
        print(f"DEBUG: Processing question with document-only approach: {question}")
        docs = None
        if getattr(pdf_processor, 'use_database_storage', False):
            docs = pdf_processor.query_document_vectors(doc_id, question, k=4)
            # docs is a list of dicts with 'page' and 'text'
            context = "\n\n".join([f"Page {d.get('page', 'N/A')}: {d.get('text', '')}" for d in docs[:3]])
        else:
            vs = pdf_processor.load_vectorstore(doc_id)
            docs = vs.similarity_search(question, k=4)
            # docs is a list of objects with .metadata and .page_content
            context = "\n\n".join([f"Page {d.metadata.get('page', 'N/A')}: {d.page_content}" for d in docs[:3]])

        if not docs:
            return "I couldn't find any relevant information in the document to answer your question."

        # Use LLM to generate a response based on the context
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        prompt = f"""Based on the following context from the document, answer the user's question concisely.

Context:
{context}

User question: {question}

Provide a helpful and accurate answer:"""

        rag_response = llm.invoke(prompt)
        return rag_response.content

    except Exception as e:
        print(f"DEBUG: Error in document RAG: {e}")
        return f"I encountered an error while processing your question. Please try rephrasing your question or check if the document is properly loaded."

@tool
def quick_page_analysis(doc_id: str, page_number: int = 1) -> str:
    """Fast text-only analysis of a specific page without image processing."""
    try:
        doc_info = pdf_processor.get_document_info(doc_id)
        reader = PdfReader(doc_info["pdf_path"])
        
        if page_number > len(reader.pages):
            return f"Error: Page {page_number} does not exist. Document has {len(reader.pages)} pages."
        
        # Extract text from the specific page
        page = reader.pages[page_number - 1]
        raw_text = page.extract_text()
        
        if not raw_text or len(raw_text.strip()) < 10:
            return f"Page {page_number} contains primarily visual content with minimal extractable text. Consider using visual analysis for detailed information."
        
        # Quick text-based analysis using LLM
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        analysis_prompt = f"""Analyze the text content from this document page and provide a concise summary.

Page {page_number} content:
{raw_text}

Provide a brief but informative summary of the key information on this page:"""
        
        response = llm.invoke(analysis_prompt)
        return response.content
        
    except Exception as e:
        return f"Error analyzing page: {str(e)}"

@tool
def answer_question_using_rag(doc_id: str, question: str) -> str:
    """Answer questions using hybrid approach with citations, combining document and web content."""
    try:
        print(f"DEBUG: Processing question with hybrid approach and citations: {question}")
        
        # Use the new hybrid search function
        result = process_question_with_hybrid_search(doc_id, question, include_suggestions=False)
        
        # Format the response as JSON with citations
        response_data = {
            "answer": result["answer"],
            "citations": result["citations"],
            "most_referenced_page": result["most_referenced_page"]
        }
        
        return json.dumps(response_data)
        
    except Exception as e:
        print(f"DEBUG: Error in hybrid RAG with citations: {e}")
        # Provide a helpful fallback response even on error
        fallback_response = {
            "answer": f"I understand you're asking about: {question}. This is an important topic that requires comprehensive analysis. Based on best practices and general knowledge, I can provide relevant insights. However, I recommend consulting current documentation, expert resources, and up-to-date information sources for the most complete and accurate understanding.",
            "citations": [],
            "most_referenced_page": None
        }
        return json.dumps(fallback_response)

def analyze_pdf_page_multimodal(doc_id: str, page_number: int = 1) -> str:
    """Optimized multimodal analysis of a PDF page using both text and visual analysis."""
    try:
        # Get document info to find PDF path
        doc_info = pdf_processor.get_document_info(doc_id)
        pdf_path = doc_info["pdf_path"]
        
        if not os.path.exists(pdf_path):
            return f"Error: PDF file not found at '{pdf_path}'"
            
        # OPTIMIZATION: Use lower DPI for faster processing (200 instead of 300)
        print(f"DEBUG: Converting page {page_number} to image for multimodal analysis (optimized)")
        images = convert_from_path(pdf_path, dpi=200, first_page=page_number, last_page=page_number)
        
        if not images:
            return f"Error: Page {page_number} not found in PDF."
            
        temp_image_path = f"temp_multimodal_page_{page_number}_{uuid.uuid4().hex[:8]}.png"
        images[0].save(temp_image_path, "PNG")
        print(f"DEBUG: Saved temporary image: {temp_image_path}")
        
        # Extract text from the specified page using pypdf
        reader = PdfReader(pdf_path)
        if page_number > len(reader.pages):
            return f"Error: Page {page_number} does not exist in the document (total pages: {len(reader.pages)})"
            
        # Get the page object
        page = reader.pages[page_number - 1]
        
        # Extract text and check if it's empty or just indicates no text was extracted
        raw_text = page.extract_text()
        if not raw_text or '[No text extracted:' in raw_text:
            page_text = "This page appears to contain primarily visual elements such as diagrams, drawings, or images. No machine-readable text could be extracted from this page." 
        else:
            page_text = raw_text
        
        # Use multimodal LLM to analyze both image and text
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        
        # OPTIMIZATION: Shorter, more focused prompt for faster processing
        message_content = [
            {
                "type": "text",
                "text": f"Analyze this document page. Describe the main visual elements, layout, rooms, doors, windows, fixtures, dimensions, labels, and text. Be concise but comprehensive.\n\nExtracted text: {page_text[:500]}\n\nProvide a focused analysis of the key elements and their relationships."
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encode_image(temp_image_path)}"}
            }
        ]
        
        message = HumanMessage(content=message_content)
        response = llm.invoke([message])
        
        # Clean up temporary image file
        try:
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
                print(f"DEBUG: Cleaned up temporary image: {temp_image_path}")
        except Exception as cleanup_error:
            print(f"DEBUG: Could not clean up temporary image {temp_image_path}: {cleanup_error}")
        
        return response.content
        
    except Exception as e:
        return f"Error analyzing PDF page: {str(e)}"

def encode_image(image_path):
    """Encode image to base64 string"""
    import base64
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

@tool
def answer_question_with_suggestions(doc_id: str, question: str) -> str:
    """Answer questions about the document using simple RAG with suggestions - no hybrid approach."""
    try:
        print(f"DEBUG: Processing question with document-only approach: {question}")
        
        # Use simple document search only
        docs = None
        if getattr(pdf_processor, 'use_database_storage', False):
            docs = pdf_processor.query_document_vectors(doc_id, question, k=6)
            context = "\n\n".join([f"Page {d.get('page', 'N/A')}: {d.get('text', '')}" for d in docs[:4]])
        else:
            vs = pdf_processor.load_vectorstore(doc_id)
            docs = vs.similarity_search(question, k=6)
            context = "\n\n".join([f"Page {d.metadata.get('page', 'N/A')}: {d.page_content}" for d in docs[:4]])

        # Generate suggestions and citations
        suggestions = []
        citations = []
        most_referenced_page = None
        if docs:
            for i, d in enumerate(docs[:3]):
                if isinstance(d, dict):
                    page = d.get('page', 'N/A')
                    text = d.get('text', '')
                else:
                    page = getattr(d, 'metadata', {}).get('page', 'N/A') if hasattr(d, 'metadata') else 'N/A'
                    text = getattr(d, 'page_content', '')
                suggestions.append({
                    "title": f"Page {page} Content",
                    "page": page,
                    "description": f"Additional information available on page {page}."
                })
                citations.append({
                    "id": i + 1,
                    "page": page,
                    "text": text,
                    "relevance_score": 1.0,
                    "doc_id": doc_id
                })
            most_referenced_page = citations[0]["page"] if citations else None

        # Use LLM to generate a response based on the context
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        prompt = f"""Based on the following context from the document, answer the user's question and provide related topic suggestions with page numbers.

Context:
{context}

User question: {question}

Provide a helpful and accurate answer. Include suggestions and cite relevant pages."""
        rag_response = llm.invoke(prompt)

        response_data = {
            "answer": rag_response.content,
            "suggestions": suggestions,
            "citations": citations,
            "most_referenced_page": most_referenced_page,
            "source_info": {
                "has_document_content": bool(docs),
                "has_web_content": False
            }
        }
        return json.dumps(response_data)
        for page_num in relevant_pages[:3]:  # Max 3 suggestions
            suggestions.append({
                "title": f"Page {page_num} Content",
                "page": page_num,
                "description": f"Additional information available on page {page_num}."
            })
        
        response_data = {
            "answer": response_text,
            "suggestions": suggestions,
            "citations": citations,
            "most_referenced_page": most_referenced_page
        }
        
        return json.dumps(response_data)
        
    except Exception as e:
        print(f"DEBUG: Error in document RAG with suggestions: {e}")
        # Provide a simple fallback response
        fallback_response = {
            "answer": f"I encountered an error while processing your question about: {question}. Please try rephrasing your question or check if the document is properly loaded.",
            "suggestions": [],
            "citations": [],
            "most_referenced_page": None
        }
        return json.dumps(fallback_response)


@tool
def save_annotated_image_as_pdf_page(image_path: str, original_pdf_path: str, page_number: int, output_pdf_path: str) -> str:
    """Convert the annotated image back to PDF page and merge with the rest of the original PDF."""
    try:
        if not os.path.exists(image_path):
            return f"Error: Annotated image not found at '{image_path}'."

        if not os.path.exists(original_pdf_path):
            return f"Error: Original PDF not found at '{original_pdf_path}'."

        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

        # Create a temporary PDF from the annotated image
        temp_pdf_path = f"temp_annotated_page_{page_number}_{uuid.uuid4().hex}.pdf"
        Image.open(image_path).save(temp_pdf_path, "PDF", resolution=100.0)

        # Read the original PDF
        reader = PdfReader(original_pdf_path)
        writer = PdfWriter()

        # Add all pages except the one we're replacing
        for i, page in enumerate(reader.pages, 1):
            if i == page_number:
                # Add the annotated page
                annotated_reader = PdfReader(temp_pdf_path)
                writer.add_page(annotated_reader.pages[0])
            else:
                writer.add_page(page)

        # Save the final PDF
        with open(output_pdf_path, "wb") as output_file:
            writer.write(output_file)

        # Clean up temporary files
        try:
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
            # Only remove temp image files (not user-generated ones)
            if os.path.exists(image_path) and "temp_floor_plan_page_" in image_path:
                os.remove(image_path)
                print(f"DEBUG: Cleaned up temporary image: {image_path}")
        except Exception as cleanup_error:
            print(f"DEBUG: Could not clean up temporary files: {cleanup_error}")

        # Verify the output file was created
        if os.path.exists(output_pdf_path):
            return f"SUCCESS: Annotated PDF saved successfully to '{output_pdf_path}'. File size: {os.path.getsize(output_pdf_path)} bytes."
        else:
            return f"Error: Failed to create output PDF at '{output_pdf_path}'."

    except Exception as e:
        return f"Error saving annotated PDF: {str(e)}"

@tool
def internet_search(query: str) -> str:
    """Search the internet for up-to-date information when needed to answer user queries."""
    try:
        # Initialize Tavily search tool with configuration from settings
        tavily_search = TavilySearch(
            max_results=5,
            topic="general",
            include_answer=True,
            include_raw_content=False,
            include_images=False
        )
        
        # Execute the search
        result = tavily_search.invoke({"query": query})
        
        # Format and return the results
        formatted_result = {
            "query": query,
            "results": result.get("results", []),
            "answer": result.get("answer", "")
        }
        
        return json.dumps(formatted_result)
    except Exception as e:
        return json.dumps({"error": f"Internet search failed: {str(e)}"})

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
    answer_question_using_rag,  # Fast text-only RAG
    answer_question_with_suggestions,  # Optimized smart analysis
    quick_page_analysis  # Fast text-only page analysis
]