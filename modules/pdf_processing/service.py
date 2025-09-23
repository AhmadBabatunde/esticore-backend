"""
PDF processing and document management for the Floor Plan Agent API
"""
import os
import uuid
from typing import List
from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document

from modules.config.settings import settings
from modules.database.models import db_manager

class PDFProcessor:
    """PDF processing and indexing service"""
    
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
        self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
    
    def pdf_to_documents(self, pdf_path: str, doc_id: str) -> List[Document]:
        """Convert PDF to document chunks for indexing"""
        reader = PdfReader(pdf_path)
        docs: List[Document] = []
        
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                # Keep empty pages indexable for page grounding
                text = f"[No text extracted: page {i}]"
            
            for chunk in self.text_splitter.split_text(text):
                docs.append(Document(
                    page_content=chunk, 
                    metadata={"doc_id": doc_id, "page": i}
                ))
        
        return docs
    
    def index_pdf(self, doc_id: str, pdf_path: str) -> int:
        """Index PDF into vector store"""
        docs = self.pdf_to_documents(pdf_path, doc_id)
        if not docs:
            raise ValueError("No text extracted from PDF")
        
        vs = FAISS.from_documents(docs, self.embeddings)
        vs.save_local(os.path.join(settings.VECTORS_DIR, doc_id))
        
        return len(docs)
    
    def load_vectorstore(self, doc_id: str) -> FAISS:
        """Load vector store for a document"""
        path = os.path.join(settings.VECTORS_DIR, doc_id)
        if not os.path.exists(path):
            raise FileNotFoundError("Vectorstore for doc not found.")
        
        return FAISS.load_local(path, self.embeddings, allow_dangerous_deserialization=True)
    
    def upload_and_index_pdf(self, file_content: bytes, filename: str, user_id: int) -> dict:
        """Upload and index a PDF file"""
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Please upload a PDF file")
        
        doc_id = uuid.uuid4().hex
        pdf_path = os.path.join(settings.DOCS_DIR, f"{doc_id}.pdf")
        
        # Save the file
        with open(pdf_path, "wb") as f:
            f.write(file_content)
        
        # Index into vector store
        try:
            n_chunks = self.index_pdf(doc_id, pdf_path)
        except Exception as e:
            # Clean up the file if indexing fails
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            raise ValueError(f"Indexing failed: {e}")
        
        # Get page count
        reader = PdfReader(pdf_path)
        num_pages = len(reader.pages)
        
        # Get vector path
        vector_path = os.path.join(settings.VECTORS_DIR, doc_id)
        
        # Save document info to database
        try:
            db_manager.create_document(
                doc_id=doc_id,
                filename=filename,
                pdf_path=pdf_path,
                vector_path=vector_path,
                pages=num_pages,
                chunks_indexed=n_chunks,
                user_id=user_id
            )
        except Exception as e:
            # Clean up files if database save fails
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            # Also clean up vector store
            if os.path.exists(vector_path):
                import shutil
                shutil.rmtree(vector_path)
            raise ValueError(f"Database save failed: {e}")
        
        return {
            "doc_id": doc_id,
            "filename": filename,
            "pages": num_pages,
            "chunks_indexed": n_chunks
        }
    
    def upload_and_index_multiple_pdfs(self, file_contents: List[bytes], filenames: List[str], user_id: int) -> List[dict]:
        """Upload and index multiple PDF files"""
        results = []
        errors = []
        
        for i, (file_content, filename) in enumerate(zip(file_contents, filenames)):
            try:
                result = self.upload_and_index_pdf(file_content, filename, user_id)
                results.append(result)
            except Exception as e:
                error_info = {
                    "filename": filename,
                    "error": str(e),
                    "index": i
                }
                errors.append(error_info)
        
        return {
            "successful_uploads": results,
            "failed_uploads": errors,
            "total_files": len(file_contents),
            "successful_count": len(results),
            "failed_count": len(errors)
        }
    
    def get_document_info(self, doc_id: str) -> dict:
        """Get document information"""
        document = db_manager.get_document_by_doc_id(doc_id)
        if not document:
            raise FileNotFoundError("Document not found")
        
        # Check if PDF file and vector store still exist
        pdf_exists = os.path.exists(document.pdf_path)
        vector_exists = os.path.exists(document.vector_path)
        
        if not pdf_exists or not vector_exists:
            missing_files = []
            if not pdf_exists:
                missing_files.append("PDF")
            if not vector_exists:
                missing_files.append("vectors")
            
            status = f"missing_{'+'.join(missing_files).lower()}"
            # Update status in database
            db_manager.update_document_status(doc_id, status)
            return {
                "doc_id": doc_id,
                "filename": document.filename,
                "pdf_path": document.pdf_path,
                "vector_path": document.vector_path,
                "pages": document.pages,
                "status": status
            }
        
        return {
            "doc_id": doc_id,
            "filename": document.filename,
            "pdf_path": document.pdf_path,
            "vector_path": document.vector_path,
            "pages": document.pages,
            "status": document.status
        }
    
    def list_documents(self, user_id: int = None) -> dict:
        """List all documents in the database"""
        if user_id:
            documents = db_manager.get_user_documents(user_id)
        else:
            documents = db_manager.get_all_documents()
        
        # Convert to dictionary format and add file existence check
        result = {}
        for doc in documents:
            doc_info = {
                "filename": doc.filename,
                "pdf_path": doc.pdf_path,
                "vector_path": doc.vector_path,
                "pages": doc.pages,
                "chunks_indexed": doc.chunks_indexed,
                "status": doc.status,
                "user_id": doc.user_id,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
            }
            
            # Check if PDF file and vector store still exist
            pdf_exists = os.path.exists(doc.pdf_path)
            vector_exists = os.path.exists(doc.vector_path)
            
            if not pdf_exists or not vector_exists:
                missing_files = []
                if not pdf_exists:
                    missing_files.append("PDF")
                if not vector_exists:
                    missing_files.append("vectors")
                
                new_status = f"missing_{'+'.join(missing_files).lower()}"
                if doc.status != new_status:
                    db_manager.update_document_status(doc.doc_id, new_status)
                doc_info["status"] = new_status
            
            result[doc.doc_id] = doc_info
        
        return result
    
    def query_document(self, doc_id: str, question: str, k: int = 5) -> dict:
        """Query document using RAG"""
        # Check if document exists in database
        document = db_manager.get_document_by_doc_id(doc_id)
        if not document:
            raise FileNotFoundError("Document not found")
        
        # Check if PDF file exists
        if not os.path.exists(document.pdf_path):
            db_manager.update_document_status(doc_id, "missing_pdf")
            raise FileNotFoundError("PDF file not found")
        
        # Check if vector store exists
        if not os.path.exists(document.vector_path):
            db_manager.update_document_status(doc_id, "missing_vectors")
            raise FileNotFoundError("Vector store not found")
        
        try:
            vs = self.load_vectorstore(doc_id)
            docs = vs.similarity_search(question, k=int(k))
            
            return {
                "doc_id": doc_id,
                "question": question,
                "matches": [
                    {
                        "page": d.metadata.get("page"),
                        "text": d.page_content
                    } for d in docs
                ]
            }
        except Exception as e:
            raise ValueError(f"Query failed: {str(e)}")
    
    def query_document_with_citations(self, doc_id: str, question: str, k: int = 5) -> dict:
        """Query document using RAG with detailed citation information"""
        # Check if document exists in database
        document = db_manager.get_document_by_doc_id(doc_id)
        if not document:
            raise FileNotFoundError("Document not found")
        
        # Check if PDF file exists
        if not os.path.exists(document.pdf_path):
            db_manager.update_document_status(doc_id, "missing_pdf")
            raise FileNotFoundError("PDF file not found")
        
        # Check if vector store exists
        if not os.path.exists(document.vector_path):
            db_manager.update_document_status(doc_id, "missing_vectors")
            raise FileNotFoundError("Vector store not found")
        
        try:
            vs = self.load_vectorstore(doc_id)
            docs = vs.similarity_search_with_score(question, k=int(k))
            
            # Process documents and organize by page
            citations_by_page = {}
            all_citations = []
            
            for i, (doc, score) in enumerate(docs):
                page_num = doc.metadata.get("page", 1)
                citation = {
                    "id": i + 1,
                    "page": page_num,
                    "text": doc.page_content,
                    "relevance_score": float(score),
                    "doc_id": doc_id
                }
                
                all_citations.append(citation)
                
                if page_num not in citations_by_page:
                    citations_by_page[page_num] = []
                citations_by_page[page_num].append(citation)
            
            # Find the most referenced page (page with most chunks)
            most_referenced_page = None
            max_citations = 0
            
            if citations_by_page:
                for page_num, page_citations in citations_by_page.items():
                    if len(page_citations) > max_citations:
                        max_citations = len(page_citations)
                        most_referenced_page = page_num
            
            return {
                "doc_id": doc_id,
                "question": question,
                "citations": all_citations,
                "citations_by_page": citations_by_page,
                "most_referenced_page": most_referenced_page,
                "total_citations": len(all_citations),
                "pages_referenced": list(citations_by_page.keys()) if citations_by_page else []
            }
        except Exception as e:
            raise ValueError(f"Query failed: {str(e)}")
    
    def get_page_citations_summary(self, doc_id: str, question: str, k: int = 8) -> dict:
        """Get a summary of which pages are most relevant to a query"""
        try:
            result = self.query_document_with_citations(doc_id, question, k)
            
            # Count citations per page and calculate relevance scores
            page_summary = {}
            for page_num, citations in result["citations_by_page"].items():
                total_relevance = sum(c["relevance_score"] for c in citations)
                avg_relevance = total_relevance / len(citations) if citations else 0
                
                page_summary[page_num] = {
                    "page": page_num,
                    "citation_count": len(citations),
                    "total_relevance_score": total_relevance,
                    "avg_relevance_score": avg_relevance,
                    "citations": citations
                }
            
            # Sort pages by citation count, then by average relevance
            sorted_pages = sorted(
                page_summary.values(),
                key=lambda x: (x["citation_count"], x["avg_relevance_score"]),
                reverse=True
            )
            
            return {
                "doc_id": doc_id,
                "question": question,
                "most_relevant_page": sorted_pages[0]["page"] if sorted_pages else None,
                "page_rankings": sorted_pages,
                "total_pages_referenced": len(sorted_pages)
            }
        except Exception as e:
            raise ValueError(f"Citation summary failed: {str(e)}")
    
    def delete_document_files(self, doc_id: str) -> bool:
        """Delete both PDF and vector files for a document"""
        success = True
        
        # Get document info from database
        document = db_manager.get_document_by_doc_id(doc_id)
        if not document:
            return False
        
        # Delete PDF file
        try:
            if os.path.exists(document.pdf_path):
                os.remove(document.pdf_path)
                print(f"Deleted PDF file: {document.pdf_path}")
        except Exception as e:
            print(f"Error deleting PDF file {document.pdf_path}: {e}")
            success = False
        
        # Delete vector store directory
        try:
            if os.path.exists(document.vector_path):
                import shutil
                shutil.rmtree(document.vector_path)
                print(f"Deleted vector store: {document.vector_path}")
        except Exception as e:
            print(f"Error deleting vector store {document.vector_path}: {e}")
            success = False
        
        # Delete from database
        try:
            db_manager.delete_document(doc_id)
            print(f"Deleted document from database: {doc_id}")
        except Exception as e:
            print(f"Error deleting document from database {doc_id}: {e}")
            success = False
        
        return success

# Global PDF processor instance
pdf_processor = PDFProcessor()