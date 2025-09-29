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
    """Draw circles around detected objects with intelligent dynamic sizing based on object dimensions."""
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

        print(f"DEBUG: Applying intelligent circle annotation to {len(objects_to_annotate)} objects")

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        
        # Get image dimensions for scaling
        img_width, img_height = image.size
        
        # Calculate object size statistics for intelligent scaling
        object_sizes = []
        for obj in objects_to_annotate:
            bbox = obj['bbox']
            obj_width = abs(bbox[2] - bbox[0])
            obj_height = abs(bbox[3] - bbox[1])
            obj_size = max(obj_width, obj_height)  # Use largest dimension
            object_sizes.append(obj_size)
        
        if object_sizes:
            avg_size = sum(object_sizes) / len(object_sizes)
            max_size = max(object_sizes)
            min_size = min(object_sizes)
        else:
            avg_size = 50
            max_size = 100
            min_size = 10
        
        print(f"DEBUG: Object size stats - Min: {min_size:.1f}, Avg: {avg_size:.1f}, Max: {max_size:.1f} px")
        
        circle_color = (255, 0, 0)  # Red
        text_color = (0, 0, 0)      # Black text
        
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except:
            font = ImageFont.load_default()

        for obj in objects_to_annotate:
            bbox = obj['bbox']
            class_name = obj.get("class_name", "unknown")
            x1, y1, x2, y2 = bbox
            center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
            
            # Calculate object dimensions
            obj_width = abs(x2 - x1)
            obj_height = abs(y2 - y1)
            obj_size = max(obj_width, obj_height)
            
            # Intelligent radius calculation based on object size relative to image and other objects
            base_radius = 15
            
            # Scale factor based on object size relative to average
            if obj_size > avg_size * 2:  # Very large object
                scale_factor = 3.0
            elif obj_size > avg_size * 1.5:  # Large object
                scale_factor = 2.5
            elif obj_size > avg_size:  # Above average
                scale_factor = 2.0
            elif obj_size > avg_size * 0.5:  # Average size
                scale_factor = 1.5
            else:  # Small object
                scale_factor = 1.0
            
            # Additional scaling based on absolute size
            absolute_scale = min(3.0, max(0.5, obj_size / 50))
            
            # Combine both scaling factors
            final_scale = (scale_factor + absolute_scale) / 2
            
            # Calculate final radius with bounds
            radius = base_radius * final_scale
            radius = max(8, min(60, radius))  # Keep between 8-60 pixels
            
            # Adjust line width based on circle size
            line_width = max(2, min(5, int(radius / 10)))
            
            print(f"DEBUG: Object '{class_name}' - Size: {obj_size:.1f}px, Radius: {radius:.1f}px, Line: {line_width}px")
            
            # Draw the circle with appropriate line width
            draw.ellipse(
                [(center_x - radius, center_y - radius), (center_x + radius, center_y + radius)],
                outline=circle_color, width=line_width
            )
            
            # Add label with smart positioning
            text_x = max(5, min(center_x - 30, img_width - 80))
            text_y = max(5, center_y - radius - 25)
            
            # Draw text with background for readability
            try:
                bbox_text = draw.textbbox((text_x, text_y), class_name, font=font)
                text_width = bbox_text[2] - bbox_text[0]
                text_height = bbox_text[3] - bbox_text[1]
                
                # Background for text
                bg_padding = 4
                draw.rectangle(
                    [text_x - bg_padding, text_y - bg_padding,
                     text_x + text_width + bg_padding, text_y + text_height + bg_padding],
                    fill=(255, 255, 255, 230)  # Semi-transparent white
                )
                
                # Draw text
                draw.text((text_x, text_y), class_name, fill=text_color, font=font)
            except Exception as text_error:
                print(f"DEBUG: Text drawing error: {text_error}")
                draw.text((text_x, text_y), class_name, fill=text_color)

        image.save(image_path)

        size_info = f" (circle sizes adapted from {min(object_sizes):.1f}px to {max(object_sizes):.1f}px objects)" if object_sizes else ""
        
        if filter_condition:
            return f"Success: Applied dynamically sized circles to {len(objects_to_annotate)} {filter_condition} objects{size_info}."
        else:
            return f"Success: Applied dynamically sized circles to all {len(objects_to_annotate)} detected objects{size_info}."

    except Exception as e:
        return f"Error applying circles: {str(e)}"
@tool
def apply_rectangle_annotation(image_path: str = "temp_floor_plan.png", objects_json: str = "", filter_condition: str = "") -> str:
    """Draw rectangles around detected objects with intelligent dynamic sizing and object-aware padding."""
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

        print(f"DEBUG: Applying intelligent rectangle annotation to {len(objects_to_annotate)} objects")

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        
        img_width, img_height = image.size
        
        # Object-specific default sizes for intelligent scaling
        OBJECT_PROPERTIES = {
            'room': {'min_padding': 10, 'max_padding': 30, 'line_width': 6, 'font_size': 20},
            'door': {'min_padding': 8, 'max_padding': 15, 'line_width': 4, 'font_size': 16},
            'window': {'min_padding': 6, 'max_padding': 12, 'line_width': 3, 'font_size': 14},
            'table': {'min_padding': 5, 'max_padding': 10, 'line_width': 3, 'font_size': 14},
            'chair': {'min_padding': 3, 'max_padding': 8, 'line_width': 2, 'font_size': 12},
            'default': {'min_padding': 4, 'max_padding': 12, 'line_width': 3, 'font_size': 14}
        }
        
        # Calculate size statistics
        object_sizes = []
        for obj in objects_to_annotate:
            bbox = obj['bbox']
            obj_size = max(abs(bbox[2] - bbox[0]), abs(bbox[3] - bbox[1]))
            object_sizes.append(obj_size)
        
        if object_sizes:
            avg_size = sum(object_sizes) / len(object_sizes)
            max_size = max(object_sizes)
            min_size = min(object_sizes)
            size_range = max_size - min_size if max_size > min_size else 1
        else:
            avg_size = 50
            max_size = 100
            min_size = 10
            size_range = 90
        
        print(f"DEBUG: Object size range: {min_size:.1f}-{max_size:.1f}px (avg: {avg_size:.1f}px)")
        
        rectangle_color = (0, 0, 255)  # Blue
        text_color = (0, 0, 0)        # Black text
        
        for obj in objects_to_annotate:
            bbox = obj['bbox']
            class_name = obj.get("class_name", "unknown").lower()
            x1, y1, x2, y2 = bbox
            
            # Get object dimensions
            obj_width = abs(x2 - x1)
            obj_height = abs(y2 - y1)
            obj_size = max(obj_width, obj_height)
            
            # Find appropriate object properties
            obj_props = OBJECT_PROPERTIES['default']
            for obj_type, props in OBJECT_PROPERTIES.items():
                if obj_type in class_name and obj_type != 'default':
                    obj_props = props
                    break
            
            # Calculate dynamic padding based on object size and type
            size_ratio = (obj_size - min_size) / size_range
            padding_range = obj_props['max_padding'] - obj_props['min_padding']
            dynamic_padding = obj_props['min_padding'] + (padding_range * size_ratio)
            
            # Ensure reasonable bounds
            dynamic_padding = max(obj_props['min_padding'], min(obj_props['max_padding'], dynamic_padding))
            
            # Dynamic line width based on object size
            line_width = obj_props['line_width']
            if obj_size > avg_size * 2:
                line_width += 2
            elif obj_size > avg_size:
                line_width += 1
            
            # Dynamic font size
            font_size = obj_props['font_size']
            if obj_size > avg_size * 1.5:
                font_size += 2
            elif obj_size < avg_size * 0.5:
                font_size = max(10, font_size - 2)
            
            print(f"DEBUG: '{class_name}' - Size: {obj_size:.1f}px, Padding: {dynamic_padding:.1f}px, Line: {line_width}px")
            
            # Apply dynamic padding
            padded_x1 = max(0, x1 - dynamic_padding)
            padded_y1 = max(0, y1 - dynamic_padding)
            padded_x2 = min(img_width, x2 + dynamic_padding)
            padded_y2 = min(img_height, y2 + dynamic_padding)
            
            # Draw the rectangle
            draw.rectangle(
                [padded_x1, padded_y1, padded_x2, padded_y2],
                outline=rectangle_color, width=line_width
            )
            
            # Add intelligent label
            try:
                dynamic_font = ImageFont.truetype("arial.ttf", font_size)
            except:
                dynamic_font = ImageFont.load_default()
            
            # Smart label positioning
            label_options = [
                (padded_x1, padded_y1 - font_size - 5),  # Above top-left
                (padded_x1, padded_y2 + 5),              # Below bottom-left  
                (padded_x2 - 100, padded_y1 - font_size - 5),  # Above top-right
                (padded_x2 - 100, padded_y2 + 5)         # Below bottom-right
            ]
            
            # Find the best position that keeps text within image bounds
            text_x, text_y = padded_x1, padded_y1 - font_size - 5
            for option_x, option_y in label_options:
                if (0 <= option_x <= img_width - 100 and 
                    0 <= option_y <= img_height - font_size - 5):
                    text_x, text_y = option_x, option_y
                    break
            
            # Draw text with background
            bbox_text = draw.textbbox((text_x, text_y), class_name, font=dynamic_font)
            text_width = bbox_text[2] - bbox_text[0]
            text_height = bbox_text[3] - bbox_text[1]
            
            # Background for readability
            bg_padding = 4
            draw.rectangle(
                [text_x - bg_padding, text_y - bg_padding,
                 text_x + text_width + bg_padding, text_y + text_height + bg_padding],
                fill=(255, 255, 255, 240)
            )
            
            # Draw text
            draw.text((text_x, text_y), class_name, fill=text_color, font=dynamic_font)

        image.save(image_path)

        size_info = f" - adapted padding for {min_size:.1f}px to {max_size:.1f}px objects"
        
        if filter_condition:
            return f"Success: Applied intelligent rectangles to {len(objects_to_annotate)} {filter_condition} objects{size_info}."
        else:
            return f"Success: Applied intelligent rectangles to all {len(objects_to_annotate)} detected objects{size_info}."

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
@tool
def analyze_pdf_page_multimodal(doc_id: str, page_number: int = 1) -> str:
    """Optimized multimodal analysis of a PDF page using both text and visual analysis."""
    try:
        # Get document info to find PDF path
        doc_info = pdf_processor.get_document_info(doc_id)
        
        # Handle different storage types
        pdf_path = None
        if doc_info.get("storage_type") == "database":
            # For database storage, we need to get the PDF content and create a temporary file
            try:
                pdf_content = pdf_processor.get_document_content(doc_id)
                # Create a temporary file for processing
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                    temp_file.write(pdf_content)
                    pdf_path = temp_file.name
            except Exception as e:
                return f"Error retrieving document from database: {str(e)}"
        else:
            # For file storage
            pdf_path = doc_info.get("pdf_path")
        
        if not pdf_path or not os.path.exists(pdf_path):
            return f"Error: PDF file not found for document {doc_id}"
            
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
        
        # Clean up temporary PDF file if it was created for database storage
        if doc_info.get("storage_type") == "database" and pdf_path:
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    print(f"DEBUG: Cleaned up temporary PDF file: {pdf_path}")
            except Exception as pdf_cleanup_error:
                print(f"DEBUG: Error cleaning up temporary PDF file: {pdf_cleanup_error}")
        
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
            return f"SUCCESS: Annotated PDF saved successfully to '{output_pdf_path}'. If you need any further assistance or additional annotations, feel free to ask!"
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

@tool
def measure_objects(image_path: str, objects_json: str, target_object: str, reference_scale: float = None, reference_unit: str = "meters") -> str:
    """
    Measure dimensions of objects in floor plans using pixel-to-real-world conversion.
    
    Args:
        image_path: Path to the floor plan image
        objects_json: JSON string of detected objects from detect_floor_plan_objects
        target_object: The object to measure (e.g., "steel base plate", "door", "window")
        reference_scale: Optional known scale (e.g., if 100 pixels = 1 meter, pass 100)
        reference_unit: Unit of measurement ("meters", "feet", "inches", "millimeters")
    
    Returns:
        JSON string with measurement results
    """
    try:
        import math
        import cv2
        import numpy as np
        
        # Parse detected objects
        detected_objects = json.loads(objects_json)
        if not isinstance(detected_objects, list):
            return json.dumps({"error": "Invalid objects data format"})
        
        # Find target objects
        target_objects = []
        target_lower = target_object.lower()
        
        for obj in detected_objects:
            class_name = obj.get('class_name', '').lower()
            if target_lower in class_name or class_name in target_lower:
                target_objects.append(obj)
        
        if not target_objects:
            available_objects = list(set(obj.get('class_name', 'unknown') for obj in detected_objects))
            return json.dumps({
                "error": f"No '{target_object}' objects found. Available objects: {available_objects}",
                "available_objects": available_objects
            })
        
        # Load image for processing
        image = cv2.imread(image_path)
        if image is None:
            return json.dumps({"error": f"Could not load image from {image_path}"})
        
        height, width = image.shape[:2]
        
        # Calculate scale if not provided
        scale_info = None
        if reference_scale is None:
            scale_info = _auto_detect_scale(image, detected_objects)
        else:
            scale_info = {
                "pixels_per_unit": reference_scale,
                "unit": reference_unit,
                "method": "user_provided",
                "confidence": 1.0
            }
        
        if not scale_info:
            return json.dumps({
                "error": "Could not determine scale automatically. Please provide reference_scale parameter.",
                "suggestion": "Provide a reference scale like: 100 (meaning 100 pixels = 1 meter)"
            })
        
        # Measure each target object
        measurements = []
        
        for i, obj in enumerate(target_objects):
            bbox = obj['bbox']
            x1, y1, x2, y2 = bbox
            
            # Calculate dimensions in pixels
            pixel_width = abs(x2 - x1)
            pixel_height = abs(y2 - y1)
            pixel_area = pixel_width * pixel_height
            diagonal_length = math.sqrt(pixel_width**2 + pixel_height**2)
            
            # Convert to real-world units
            real_width = pixel_width / scale_info["pixels_per_unit"]
            real_height = pixel_height / scale_info["pixels_per_unit"]
            real_area = pixel_area / (scale_info["pixels_per_unit"] ** 2)
            real_diagonal = diagonal_length / scale_info["pixels_per_unit"]
            
            # Apply common object-specific adjustments
            adjusted_measurements = _apply_object_specific_adjustments(
                target_object, real_width, real_height, real_area
            )
            
            measurements.append({
                "object_id": i + 1,
                "class_name": obj.get('class_name', 'unknown'),
                "confidence": obj.get('confidence', 0),
                "pixel_measurements": {
                    "width": round(pixel_width, 2),
                    "height": round(pixel_height, 2),
                    "area": round(pixel_area, 2),
                    "diagonal": round(diagonal_length, 2)
                },
                "real_world_measurements": {
                    "width": round(real_width, 3),
                    "height": round(real_height, 3),
                    "area": round(real_area, 3),
                    "diagonal": round(real_diagonal, 3),
                    "unit": scale_info["unit"]
                },
                "adjusted_measurements": adjusted_measurements,
                "bbox": bbox
            })
        
        # Generate summary
        if measurements:
            widths = [m["real_world_measurements"]["width"] for m in measurements]
            avg_width = sum(widths) / len(widths)
            min_width = min(widths)
            max_width = max(widths)
            
            summary = {
                "total_objects_measured": len(measurements),
                "average_width": round(avg_width, 3),
                "min_width": round(min_width, 3),
                "max_width": round(max_width, 3),
                "measurement_unit": scale_info["unit"]
            }
        else:
            summary = {}
        
        result = {
            "success": True,
            "target_object": target_object,
            "scale_info": scale_info,
            "measurements": measurements,
            "summary": summary,
            "image_dimensions": {"width": width, "height": height}
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Measurement failed: {str(e)}"})

def _auto_detect_scale(image, detected_objects):
    """
    Automatically detect scale by looking for standard-sized objects.
    """
    try:
        import cv2
        import numpy as np
        
        # Common real-world dimensions (in meters)
        STANDARD_DIMENSIONS = {
            'door': 0.9,  # Standard door width
            'window': 1.2,  # Standard window width
            'table': 0.9,   # Standard table width
            'chair': 0.5,   # Standard chair width
            'toilet': 0.4,  # Standard toilet width
        }
        
        # Look for objects with known standard dimensions
        for obj in detected_objects:
            class_name = obj.get('class_name', '').lower()
            
            for standard_obj, standard_width in STANDARD_DIMENSIONS.items():
                if standard_obj in class_name:
                    bbox = obj['bbox']
                    pixel_width = abs(bbox[2] - bbox[0])
                    
                    if pixel_width > 10:  # Ensure reasonable detection
                        pixels_per_meter = pixel_width / standard_width
                        
                        return {
                            "pixels_per_unit": pixels_per_meter,
                            "unit": "meters",
                            "reference_object": class_name,
                            "reference_width_meters": standard_width,
                            "method": f"auto_detected_from_{standard_obj}",
                            "confidence": min(obj.get('confidence', 0.5), 0.8)  # Cap confidence
                        }
        
        # Fallback: Use image dimensions and typical floor plan scales
        height, width = image.shape[:2]
        
        # Assume typical residential floor plan scale
        # For a 10m room in a 1000px image, scale would be 100 px/m
        typical_scale = max(width, height) / 15.0  # Assume 15m for largest dimension
        
        return {
            "pixels_per_unit": typical_scale,
            "unit": "meters",
            "method": "estimated_from_image_size",
            "confidence": 0.3,
            "note": "This is an estimation. For accurate measurements, provide a reference scale."
        }
        
    except Exception as e:
        print(f"DEBUG: Auto-scale detection failed: {e}")
        return None

def _apply_object_specific_adjustments(object_type, width, height, area):
    """
    Apply object-specific measurement adjustments based on typical dimensions.
    """
    object_type_lower = object_type.lower()
    adjustments = {}
    
    # Steel base plate specific adjustments
    if 'steel' in object_type_lower and 'base' in object_type_lower and 'plate' in object_type_lower:
        # Steel base plates are typically square or rectangular with specific thickness
        adjustments.update({
            "likely_thickness_mm": "16-25 mm (typical structural steel)",
            "likely_material": "A36 Steel or equivalent",
            "volume_cm3": round(width * 100 * height * 100 * 0.02, 2),  # Assuming 2cm thickness
            "weight_kg": round(width * height * 0.02 * 7850, 2),  # steel density 7850 kg/m3
            "common_sizes": "150x150mm to 600x600mm for column base plates"
        })
    
    # Door specific adjustments
    elif 'door' in object_type_lower:
        adjustments.update({
            "standard_width_m": 0.9,
            "standard_height_m": 2.1,
            "type": "Interior/Exterior door based on context",
            "swing_clearance": "0.6-0.9m required"
        })
    
    # Window specific adjustments
    elif 'window' in object_type_lower:
        adjustments.update({
            "standard_height_m": 1.2,
            "sill_height_m": "0.9-1.0 typical",
            "type": "Fixed/Casement/Double-hung based on proportions"
        })
    
    # Furniture adjustments
    elif any(furniture in object_type_lower for furniture in ['table', 'desk', 'counter']):
        adjustments.update({
            "standard_height_m": 0.75,
            "typical_depth_m": 0.6 if width > 0.8 else 0.4,
            "usage_notes": "Check for ergonomic clearances"
        })
    
    elif 'chair' in object_type_lower:
        adjustments.update({
            "standard_height_m": 0.45,
            "standard_depth_m": 0.5,
            "clearance_required": "0.6-0.8m behind"
        })
    
    # Add general engineering notes
    adjustments["measurement_notes"] = [
        "Measurements are approximate based on pixel analysis",
        "Verify with actual site measurements for construction",
        "Consider manufacturing tolerances ±2mm",
        "Check local building codes for required dimensions"
    ]
    
    return adjustments

@tool
def calibrate_scale(image_path: str, known_width_pixels: float, known_width_real: float, real_unit: str = "meters") -> str:
    """
    Calibrate the measurement scale using a known dimension.
    
    Args:
        image_path: Path to the floor plan image
        known_width_pixels: Width of a known object in pixels
        known_width_real: Actual width of the object in real units
        real_unit: Unit of measurement ("meters", "feet", "inches", "millimeters")
    
    Returns:
        JSON string with calibration results
    """
    try:
        pixels_per_unit = known_width_pixels / known_width_real
        
        result = {
            "success": True,
            "calibration": {
                "pixels_per_unit": round(pixels_per_unit, 2),
                "unit": real_unit,
                "known_reference": {
                    "pixels": known_width_pixels,
                    "real_units": known_width_real,
                    "unit": real_unit
                }
            },
            "usage_example": f"Use pixels_per_unit={round(pixels_per_unit, 2)} in measure_objects tool",
            "common_conversions": {
                "pixels_per_meter": round(pixels_per_unit, 2) if real_unit == "meters" else "N/A",
                "pixels_per_foot": round(pixels_per_unit / 0.3048, 2) if real_unit == "meters" else "N/A",
                "pixels_per_inch": round(pixels_per_unit / 0.0254, 2) if real_unit == "meters" else "N/A"
            }
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Scale calibration failed: {str(e)}"})

@tool
def analyze_object_proportions(image_path: str, objects_json: str, target_object: str) -> str:
    """
    Analyze proportions and relationships between objects for design validation.
    """
    try:
        detected_objects = json.loads(objects_json)
        
        # Find target objects
        target_objects = [obj for obj in detected_objects 
                         if target_object.lower() in obj.get('class_name', '').lower()]
        
        if not target_objects:
            return json.dumps({"error": f"No '{target_object}' objects found"})
        
        proportions_analysis = []
        
        for obj in target_objects:
            bbox = obj['bbox']
            width = abs(bbox[2] - bbox[0])
            height = abs(bbox[3] - bbox[1])
            
            aspect_ratio = width / height if height > 0 else 0
            
            # Analyze proportions
            if 0.9 <= aspect_ratio <= 1.1:
                shape = "Square"
            elif aspect_ratio > 1.1:
                shape = "Horizontal Rectangle"
            else:
                shape = "Vertical Rectangle"
            
            # Golden ratio check
            golden_ratio = 1.618
            golden_deviation = abs(aspect_ratio - golden_ratio) / golden_ratio
            
            proportions_analysis.append({
                "object_id": obj.get('class_name', 'unknown'),
                "aspect_ratio": round(aspect_ratio, 3),
                "shape_classification": shape,
                "golden_ratio_deviation": f"{round(golden_deviation * 100, 1)}%",
                "width_px": round(width, 2),
                "height_px": round(height, 2),
                "design_notes": _get_design_notes(target_object, aspect_ratio)
            })
        
        return json.dumps({
            "success": True,
            "proportions_analysis": proportions_analysis,
            "target_object": target_object
        }, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Proportion analysis failed: {str(e)}"})

def _get_design_notes(object_type, aspect_ratio):
    """Provide design guidance based on object type and proportions."""
    object_type_lower = object_type.lower()
    
    if 'steel' in object_type_lower and 'base' in object_type_lower:
        if 0.8 <= aspect_ratio <= 1.2:
            return "Good proportion for base plate - provides balanced load distribution"
        elif aspect_ratio > 1.5:
            return "Consider additional stiffeners for long base plates"
        else:
            return "Verify anchor bolt placement for this aspect ratio"
    
    elif 'door' in object_type_lower:
        if 0.4 <= aspect_ratio <= 0.45:
            return "Standard door proportion (0.9x2.1m)"
        else:
            return "Non-standard door proportion - check accessibility requirements"
    
    elif 'window' in object_type_lower:
        if 1.5 <= aspect_ratio <= 2.5:
            return "Good window proportion for natural light"
        else:
            return "Consider window operation type with this proportion"
    
    return "Proportion appears reasonable for the object type"

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
    quick_page_analysis,  # Fast text-only page analysis
    measure_objects,
    calibrate_scale,
    analyze_object_proportions
]