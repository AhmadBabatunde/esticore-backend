"""
PDF processing API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List
from modules.pdf_processing.service import pdf_processor

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload")
async def upload_pdf(files: List[UploadFile] = File(...), user_id: int = Form(...)):
    """
    Upload and index PDF document(s) - supports both single and multiple files
    """
    try:
        print(f"Debug: received {len(files)} files for upload")
        
        # Validate that we have files
        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="No files provided")
        
        # Filter out empty files (common when no file is selected)
        valid_files = [f for f in files if f.filename and f.filename.strip() != '']
        
        if len(valid_files) == 0:
            raise HTTPException(status_code=400, detail="No valid files provided")
        
        print(f"Debug: processing {len(valid_files)} valid files")
        
        # Validate file types
        for file in valid_files:
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF")
        
        # Handle single file (backward compatibility)
        if len(valid_files) == 1:
            file = valid_files[0]
            file_content = await file.read()
            result = pdf_processor.upload_and_index_pdf(file_content, file.filename, user_id)
            print(f"Debug: single file upload result: {result}")
            return result
        
        # Handle multiple files
        else:
            file_contents = []
            filenames = []
            
            for file in valid_files:
                content = await file.read()
                file_contents.append(content)
                filenames.append(file.filename)
                print(f"Debug: processed file {file.filename}, size: {len(content)} bytes")
            
            result = pdf_processor.upload_and_index_multiple_pdfs(file_contents, filenames, user_id)
            print(f"Debug: multiple files upload result: {result}")
            return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Debug: Exception in upload_pdf: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/upload-multiple")
async def upload_multiple_pdfs(files: List[UploadFile] = File(...), user_id: int = Form(...)):
    """
    Upload and index multiple PDF documents
    """
    try:
        print(f"Debug: received {len(files)} files for upload")
        
        # Validate that we have files
        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="No files provided")
        
        # Check if any file has empty filename (common when no file is selected)
        valid_files = [f for f in files if f.filename and f.filename.strip() != '']
        
        if len(valid_files) == 0:
            raise HTTPException(status_code=400, detail="No valid files provided")
        
        print(f"Debug: processing {len(valid_files)} valid files")
        
        # Validate file types
        for file in valid_files:
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF")
        
        # Read file contents
        file_contents = []
        filenames = []
        
        for file in valid_files:
            content = await file.read()
            file_contents.append(content)
            filenames.append(file.filename)
            print(f"Debug: processed file {file.filename}, size: {len(content)} bytes")
        
        # Process files
        result = pdf_processor.upload_and_index_multiple_pdfs(file_contents, filenames, user_id)
        print(f"Debug: upload result: {result}")
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Debug: Exception in upload_multiple_pdfs: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/")
def list_documents(user_id: int = None):
    """
    List all uploaded documents, optionally filtered by user
    """
    return pdf_processor.list_documents(user_id)

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

@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    """
    Delete a document and all associated files (PDF and vectors)
    """
    try:
        success = pdf_processor.delete_document_files(doc_id)
        if success:
            return {"message": "Document deleted successfully", "doc_id": doc_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete document completely")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))