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
from langchain_openai import ChatOpenAI
from inference_sdk import InferenceHTTPClient

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

# @tool
# def answer_question_using_rag(doc_id: str, question: str) -> str:
#     """Answer questions about the document using RAG (Retrieval Augmented Generation)."""
@tool
def answer_question_using_rag(doc_id: str, question: str) -> str:
    """Answer questions about the document using RAG (Retrieval Augmented Generation)."""
    try:
        vs = pdf_processor.load_vectorstore(doc_id)
        docs = vs.similarity_search(question, k=5)
        
        if not docs:
            return "I couldn't find any relevant information in the document to answer your question."
        
        # Format the context
        context = "\n\n".join([f"Page {d.metadata.get('page', 'N/A')}: {d.page_content}" for d in docs])
        
        # Use LLM to generate a response based on the context
        prompt = f"""Based on the following context from the document, answer the user's question.

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
def answer_question_with_suggestions(doc_id: str, question: str) -> str:
    """Answer questions about the document using RAG and provide related topic suggestions with page numbers."""
    try:
        vs = pdf_processor.load_vectorstore(doc_id)
        docs = vs.similarity_search(question, k=8)  # Get more docs for better suggestions
        
        if not docs:
            return json.dumps({
                "answer": "I couldn't find any relevant information in the document to answer your question.",
                "suggestions": []
            })
        
        # Format the context for the main answer
        main_docs = docs[:5]  # Use top 5 for main answer
        context = "\n\n".join([f"Page {d.metadata.get('page', 'N/A')}: {d.page_content}" for d in main_docs])
        
        # Use LLM to generate the main response
        answer_prompt = f"""Based on the following context from the document, answer the user's question.

Context:
{context}

User question: {question}

Provide a helpful and accurate answer:"""
        
        llm = ChatOpenAI(model="gpt-5", temperature=0.0, api_key=settings.OPENAI_API_KEY)
        rag_response = llm.invoke(answer_prompt)
        
        # Generate topic suggestions from all retrieved documents
        all_pages_content = {}
        for doc in docs:
            page_num = doc.metadata.get('page', 1)  # Default to page 1 if N/A
            if page_num not in all_pages_content:
                all_pages_content[page_num] = []
            all_pages_content[page_num].append(doc.page_content)
        
        print(f"DEBUG: Documents from {len(all_pages_content)} pages for suggestions")
        
        # Create suggestions prompt with page-organized content
        suggestions_context = "\n\n".join([
            f"Page {page}: {' '.join(contents)}" 
            for page, contents in all_pages_content.items()
        ])
        
        suggestions_prompt = f"""Based on the following document content and the user's question, identify 3-5 related topics that the user might be interested in exploring further.

Document content:
{suggestions_context}

User question: {question}

For each related topic, provide:
1. A clear, concise topic title (2-6 words)
2. The page number where this topic can be found (use the page numbers from the context above)
3. A brief description (1-2 sentences)

Even if the content seems limited, try to identify at least 2-3 related topics based on the available content.

Format your response as a JSON array of objects with keys: "title", "page", "description".

Example format:
[
  {{
    "title": "AI Tool Usage",
    "page": 1,
    "description": "Instructions on how to use different AI annotation tools."
  }},
  {{
    "title": "Washroom Features",
    "page": 1,
    "description": "Details about washroom layouts and identification."
  }}
]

Provide only the JSON array, no additional text:"""
        
        suggestions_response = llm.invoke(suggestions_prompt)
        print(f"DEBUG: Suggestions LLM response: {suggestions_response.content}")
        
        # Parse suggestions JSON with improved error handling
        suggestions = []
        try:
            # Try to extract JSON from the response
            response_content = suggestions_response.content.strip()
            
            # Look for JSON array in the response
            json_start = response_content.find('[')
            json_end = response_content.rfind(']') + 1
            
            if json_start != -1 and json_end != -1:
                json_str = response_content[json_start:json_end]
                suggestions = json.loads(json_str)
                
            if not isinstance(suggestions, list):
                suggestions = []
                
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON parsing error: {e}")
            print(f"DEBUG: Raw response: {suggestions_response.content}")
            suggestions = []
        
        # Process suggestions with more lenient validation
        valid_suggestions = []
        for suggestion in suggestions:
            if isinstance(suggestion, dict):
                # Ensure required keys exist with defaults
                title = suggestion.get('title', 'Related Topic')
                page = suggestion.get('page', 1)
                description = suggestion.get('description', 'Additional information available.')
                
                # Convert page to integer if possible
                try:
                    if isinstance(page, str) and page.lower() != 'n/a':
                        page = int(page)
                    elif isinstance(page, str):
                        page = 1  # Default for N/A
                    elif not isinstance(page, int):
                        page = 1
                        
                    valid_suggestion = {
                        "title": str(title)[:50],  # Limit title length
                        "page": page,
                        "description": str(description)[:200]  # Limit description length
                    }
                    valid_suggestions.append(valid_suggestion)
                    
                except (ValueError, TypeError):
                    # If page conversion fails, skip this suggestion
                    continue
        
        print(f"DEBUG: Valid suggestions count: {len(valid_suggestions)}")
        
        # If no valid suggestions were generated, create fallback suggestions based on content
        if len(valid_suggestions) == 0 and docs:
            print("DEBUG: No valid suggestions generated, creating fallback suggestions")
            # Create basic suggestions based on available pages
            available_pages = set(doc.metadata.get('page', 1) for doc in docs)
            
            fallback_suggestions = []
            for page in sorted(available_pages):
                if len(fallback_suggestions) < 3:  # Limit to 3 fallback suggestions
                    fallback_suggestions.append({
                        "title": f"Page {page} Content",
                        "page": page,
                        "description": f"Additional information and details available on page {page}."
                    })
            
            valid_suggestions = fallback_suggestions
        
        result = {
            "answer": rag_response.content,
            "suggestions": valid_suggestions[:5]  # Limit to 5 suggestions
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        print(f"DEBUG: Error in answer_question_with_suggestions: {str(e)}")
        return json.dumps({
            "answer": f"Error answering question: {str(e)}",
            "suggestions": []
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
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as cleanup_error:
            print(f"DEBUG: Could not clean up temporary files: {cleanup_error}")

        # Verify the output file was created
        if os.path.exists(output_pdf_path):
            return f"SUCCESS: Annotated PDF saved successfully to '{output_pdf_path}'. File size: {os.path.getsize(output_pdf_path)} bytes."
        else:
            return f"Error: Failed to create output PDF at '{output_pdf_path}'."

    except Exception as e:
        return f"Error saving annotated PDF: {str(e)}"

# List of all available tools
ALL_TOOLS = [
    load_pdf_for_floorplan,
    convert_pdf_page_to_image,
    detect_floor_plan_objects,
    verify_detections,
    apply_highlight_annotation,
    apply_circle_annotation,
    apply_rectangle_annotation,
    apply_count_annotation,
    apply_arrow_annotation,
    save_annotated_image_as_pdf_page,
    answer_question_using_rag,
    answer_question_with_suggestions
]