"""
Agent tools for floor plan processing and annotation
"""
import os
import json
import uuid
import tempfile
from typing import List
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
            "message": ""
        }

        requested_object_lower = requested_object.lower()
        if any(requested_object_lower in cls for cls in class_counts.keys()):
            response['requested_object_found'] = True
            response['message'] = f"Verification successful: Detections include objects matching '{requested_object}'."
        else:
            response['message'] = f"Verification failed: No objects matching '{requested_object}' were detected. Available classes: {sorted(list(class_counts.keys()))}"

        return json.dumps(response, indent=2)

    except Exception as e:
        return f"Error verifying detections: {str(e)}"

@tool
def answer_question_using_rag(doc_id: str, question: str) -> str:
    """Fast text-only RAG for questions that don't require visual analysis."""
    try:
        vs = pdf_processor.load_vectorstore(doc_id)
        docs = vs.similarity_search(question, k=4)  # Reduced for speed
        
        if not docs:
            return "I couldn't find any relevant information in the document to answer your question."
        
        # Format the context (text only, no image analysis)
        context = "\n\n".join([f"Page {d.metadata.get('page', 'N/A')}: {d.page_content}" for d in docs[:3]])
        
        # Use LLM to generate a response based on the context
        prompt = f"""Based on the following context from the document, answer the user's question concisely.

Context:
{context}

User question: {question}

Provide a helpful and accurate answer:"""
        
        llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        rag_response = llm.invoke(prompt)
        
        return rag_response.content
        
    except Exception as e:
        return f"Error answering question: {str(e)}"

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
        llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=settings.OPENAI_API_KEY)
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
    """Answer questions about the document using RAG (Retrieval Augmented Generation) with citations."""
    try:
        # Get citations and context
        try:
            citation_result = pdf_processor.query_document_with_citations(doc_id, question, k=5)
            citations = citation_result.get("citations", [])
            page_summary = pdf_processor.get_page_citations_summary(doc_id, question, k=5)
            most_referenced_page = page_summary.get("most_relevant_page")
        except Exception as e:
            print(f"DEBUG: Error getting citations, falling back to basic RAG: {e}")
            # Fallback to basic processing
            vs = pdf_processor.load_vectorstore(doc_id)
            docs = vs.similarity_search(question, k=5)
            
            if not docs:
                return json.dumps({
                    "answer": "I couldn't find any relevant information in the document to answer your question.",
                    "citations": [],
                    "most_referenced_page": None
                })
            
            # Create basic citations from docs
            citations = []
            for i, doc in enumerate(docs):
                citations.append({
                    "id": i + 1,
                    "page": doc.metadata.get("page", 1),
                    "text": doc.page_content,
                    "relevance_score": 0.8,  # Default score
                    "doc_id": doc_id
                })
            
            # Find most referenced page
            page_counts = {}
            for citation in citations:
                page = citation["page"]
                page_counts[page] = page_counts.get(page, 0) + 1
            
            most_referenced_page = max(page_counts.items(), key=lambda x: x[1])[0] if page_counts else None
        
        if not citations:
            return json.dumps({
                "answer": "I couldn't find any relevant information in the document to answer your question.",
                "citations": [],
                "most_referenced_page": None
            })
        
        # Format the context from citations
        context = "\n\n".join([f"Page {c['page']}: {c['text']}" for c in citations[:4]])
        
        # Create citation references for the prompt
        citation_text = "\n\nCitation references:\n"
        for citation in citations[:4]:  # Include up to 4 citations
            citation_text += f"[{citation['id']}] Page {citation['page']}\n"
        
        # Use LLM to generate a response based on the context
        prompt = f"""Based on the following context from the document, answer the user's question.

Context:
{context}

User question: {question}

Provide a helpful and accurate answer. IMPORTANT: Include citation references in your response using the format [1], [2], etc. to reference the source pages. Add a citations section at the end listing the page numbers.

Available citations:
{citation_text}"""
        
        llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        rag_response = llm.invoke(prompt)
        
        # Ensure the response includes proper citations by adding them if missing
        response_text = rag_response.content
        if not any(f"[{i}]" in response_text for i in range(1, 5)):
            # If no citations were included, add them at the end
            response_text += "\n\nSources:"
            for citation in citations[:3]:  # Show top 3 sources
                response_text += f"\n- Page {citation['page']}"
        
        return json.dumps({
            "answer": response_text,
            "citations": citations,
            "most_referenced_page": most_referenced_page
        })
        
    except Exception as e:
        return json.dumps({
            "answer": f"Error answering question: {str(e)}",
            "citations": [],
            "most_referenced_page": None
        })

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
        llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        
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
    """Answer questions about the document using optimized processing with smart image analysis fallback and citations."""
    try:
        # Check if the question is asking about a specific page
        import re
        page_match = re.search(r'\bpage\s+(\d+)\b', question.lower())
        specific_page = int(page_match.group(1)) if page_match else None
        
        # OPTIMIZATION 1: Fast text-only check first
        # Check if we can answer the question with text alone before using image analysis
        can_use_text_only = not any(keyword in question.lower() for keyword in [
            'layout', 'arrangement', 'position', 'where', 'located', 'diagram', 'drawing', 
            'plan', 'design', 'visual', 'look', 'appearance', 'orientation', 'spatial', 
            'show', 'see', 'view', 'display', 'illustrate', 'color', 'shape', 'size'
        ])
        
        # If asking about a specific page, use optimized direct analysis
        if specific_page:
            print(f"DEBUG: Direct page request detected for page {specific_page}")
            
            try:
                doc_info = pdf_processor.get_document_info(doc_id)
                reader = PdfReader(doc_info["pdf_path"])
                
                if specific_page > len(reader.pages):
                    return json.dumps({
                        "answer": f"Error: Page {specific_page} does not exist. Document has {len(reader.pages)} pages.",
                        "suggestions": [],
                        "citations": [],
                        "most_referenced_page": None
                    })
                
                # Extract text from the specific page
                page = reader.pages[specific_page - 1]
                raw_text = page.extract_text()
                has_meaningful_text = raw_text and len(raw_text.strip()) > 20 and '[No text extracted:' not in raw_text
                
                # OPTIMIZATION 2: Use text-only analysis when possible
                if has_meaningful_text and can_use_text_only:
                    print(f"DEBUG: Page {specific_page} has sufficient text, using text-only analysis (FAST)")
                    
                    llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=settings.OPENAI_API_KEY)
                    answer_prompt = f"""Based on the text content from page {specific_page}, answer the user's question.

Page {specific_page} content:
{raw_text}

User question: {question}

Provide a comprehensive answer and include a citation reference at the end in the format: [Source: Page {specific_page}]"""
                    
                    rag_response = llm.invoke(answer_prompt)
                    
                    # Create a simple citation for this page
                    citation = {
                        "id": 1,
                        "page": specific_page,
                        "text": raw_text[:200] + "..." if len(raw_text) > 200 else raw_text,
                        "relevance_score": 1.0,
                        "doc_id": doc_id
                    }
                    
                    return json.dumps({
                        "answer": rag_response.content,
                        "suggestions": [{
                            "title": f"Page {specific_page} Content",
                            "page": specific_page,
                            "description": "Detailed text-based analysis of this page's content."
                        }],
                        "citations": [citation],
                        "most_referenced_page": specific_page
                    })
                
                # OPTIMIZATION 3: Only use multimodal for visual questions or pages without text
                elif not has_meaningful_text or not can_use_text_only:
                    print(f"DEBUG: Page {specific_page} requires visual analysis - text insufficient or visual question")
                    multimodal_result = analyze_pdf_page_multimodal(doc_id, specific_page)
                    
                    # Add citation reference to visual analysis
                    visual_result_with_citation = f"{multimodal_result}\n\n[Source: Page {specific_page} - Visual Analysis]"
                    
                    # Create a simple citation for visual analysis
                    citation = {
                        "id": 1,
                        "page": specific_page,
                        "text": "Visual analysis of page content",
                        "relevance_score": 1.0,
                        "doc_id": doc_id
                    }
                    
                    return json.dumps({
                        "answer": visual_result_with_citation,
                        "suggestions": [{
                            "title": f"Page {specific_page} Visual Analysis",
                            "page": specific_page,
                            "description": "Visual analysis of architectural elements and layout."
                        }],
                        "citations": [citation],
                        "most_referenced_page": specific_page
                    })
                
            except Exception as e:
                print(f"DEBUG: Error in direct page analysis: {e}")
                # Fall through to regular processing
        
        # OPTIMIZATION 4: Smart RAG with minimal image analysis and citations
        # Only use RAG for multi-page questions or when specific page isn't requested
        print(f"DEBUG: Using optimized multi-page analysis with citations (text-focused)")
        
        # Get citations and page summary
        try:
            citation_result = pdf_processor.query_document_with_citations(doc_id, question, k=6)
            page_summary = pdf_processor.get_page_citations_summary(doc_id, question, k=6)
            most_referenced_page = page_summary.get("most_relevant_page")
            
            citations = citation_result.get("citations", [])
            print(f"DEBUG: Found {len(citations)} citations across {len(citation_result.get('pages_referenced', []))} pages")
            
        except Exception as e:
            print(f"DEBUG: Error getting citations, falling back to regular RAG: {e}")
            # Fallback to regular processing without citations
            vs = pdf_processor.load_vectorstore(doc_id)
            docs = vs.similarity_search(question, k=6)
            citations = []
            most_referenced_page = None
            
            if docs:
                for i, doc in enumerate(docs):
                    citations.append({
                        "id": i + 1,
                        "page": doc.metadata.get("page", 1),
                        "text": doc.page_content,
                        "relevance_score": 0.8,  # Default score
                        "doc_id": doc_id
                    })
                
                # Find most referenced page
                page_counts = {}
                for citation in citations:
                    page = citation["page"]
                    page_counts[page] = page_counts.get(page, 0) + 1
                
                if page_counts:
                    most_referenced_page = max(page_counts.items(), key=lambda x: x[1])[0]
        
        if not citations:
            return json.dumps({
                "answer": "I couldn't find any relevant information in the document to answer your question.",
                "suggestions": [],
                "citations": [],
                "most_referenced_page": None
            })
        
        # Format context from citations
        main_citations = citations[:4]  # Reduced from 5 for speed
        context = "\n\n".join([f"Page {c['page']}: {c['text']}" for c in main_citations])
        
        # OPTIMIZATION 5: Only analyze images for pages that definitely need it
        relevant_pages = list(set(c["page"] for c in main_citations))
        multimodal_analysis = ""
        
        # Only do image analysis if:
        # 1. Question explicitly requires visual understanding, AND
        # 2. We found pages with no text content
        if not can_use_text_only:
            print(f"DEBUG: Visual question detected, checking for pages with no text")
            
            pages_needing_visual = []
            doc_info = pdf_processor.get_document_info(doc_id)
            reader = PdfReader(doc_info["pdf_path"])
            
            # Check only the most relevant pages (max 2 for speed)
            for page_num in relevant_pages[:2]:
                try:
                    if page_num <= len(reader.pages):
                        page = reader.pages[page_num - 1]
                        raw_text = page.extract_text()
                        if not raw_text or len(raw_text.strip()) < 20 or '[No text extracted:' in raw_text:
                            pages_needing_visual.append(page_num)
                except Exception as e:
                    print(f"Error checking text for page {page_num}: {e}")
            
            # Only analyze pages that truly need visual analysis (max 1 for speed)
            if pages_needing_visual:
                print(f"DEBUG: Analyzing {len(pages_needing_visual[:1])} pages visually")
                for page_num in pages_needing_visual[:1]:  # Limit to 1 page for speed
                    try:
                        analysis = analyze_pdf_page_multimodal(doc_id, page_num)
                        multimodal_analysis += f"\n\nVisual analysis of page {page_num}:\n{analysis}"
                    except Exception as e:
                        print(f"DEBUG: Error in multimodal analysis for page {page_num}: {e}")
                        continue
            else:
                print(f"DEBUG: All relevant pages have sufficient text, skipping image analysis")
        
        # Generate answer using available context
        llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        
        enhanced_context = context
        if multimodal_analysis:
            enhanced_context += f"\n\nAdditional visual analysis:{multimodal_analysis}"
        
        # Create citation references for the prompt
        citation_text = "\n\nCitation references:\n"
        for citation in citations[:5]:  # Include up to 5 citations
            citation_text += f"[{citation['id']}] Page {citation['page']}\n"
            
        answer_prompt = f"""Based on the following context from the document, answer the user's question.

Context:
{enhanced_context}

User question: {question}

Provide a helpful and accurate answer. IMPORTANT: Include citation references in your response using the format [1], [2], etc. to reference the source pages. Add a citations section at the end listing the page numbers.

Available citations:
{citation_text}"""
        
        rag_response = llm.invoke(answer_prompt)
        
        # Ensure the response includes proper citations by adding them if missing
        response_text = rag_response.content
        if not any(f"[{i}]" in response_text for i in range(1, 6)):
            # If no citations were included, add them at the end
            response_text += "\n\nSources:"
            for citation in citations[:3]:  # Show top 3 sources
                response_text += f"\n- Page {citation['page']}"
        
        # Generate lightweight suggestions (reduced complexity)
        suggestions = []
        for i, page_num in enumerate(relevant_pages[:3]):  # Max 3 suggestions
            suggestions.append({
                "title": f"Page {page_num} Content",
                "page": page_num,
                "description": f"Additional information available on page {page_num}."
            })
        
        return json.dumps({
            "answer": response_text,
            "suggestions": suggestions,
            "citations": citations,
            "most_referenced_page": most_referenced_page
        })
        
    except Exception as e:
        print(f"DEBUG: Error in optimized answer_question_with_suggestions: {str(e)}")
        return json.dumps({
            "answer": f"Error processing question: {str(e)}",
            "suggestions": [],
            "citations": [],
            "most_referenced_page": None
        })

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
    """Search the internet for up-to-date information when needed to answer user queries or when
    user questions require more detailed information beyond the available context"""
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