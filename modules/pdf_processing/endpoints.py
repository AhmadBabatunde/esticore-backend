"""
PDF processing API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from modules.pdf_processing.service import pdf_processor

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload and index a PDF document
    """
    try:
        file_content = await file.read()
        result = pdf_processor.upload_and_index_pdf(file_content, file.filename)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/")
def list_documents():
    """
    List all uploaded documents
    """
    return pdf_processor.list_documents()

@router.get("/{doc_id}")
def get_document_info(doc_id: str):
    """
    Get information about a specific document
    """
    try:
        return pdf_processor.get_document_info(doc_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{doc_id}/pages")
def get_document_pages(doc_id: str):
    """
    Get page count for a document
    """
    try:
        info = pdf_processor.get_document_info(doc_id)
        return {"doc_id": doc_id, "pages": info["pages"]}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{doc_id}/query")
async def query_document(doc_id: str, question: str = Form(...), k: int = Form(5)):
    """
    Query a document using RAG (Retrieval Augmented Generation)
    """
    try:
        result = pdf_processor.query_document(doc_id, question, k)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))