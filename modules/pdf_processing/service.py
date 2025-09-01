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
from modules.config.utils import load_registry, save_registry

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
    
    def upload_and_index_pdf(self, file_content: bytes, filename: str) -> dict:
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
        
        # Update registry
        reg = load_registry()
        reg[doc_id] = {"pdf_path": pdf_path, "filename": filename}
        save_registry(reg)
        
        # Get page count
        reader = PdfReader(pdf_path)
        num_pages = len(reader.pages)
        
        return {
            "doc_id": doc_id,
            "filename": filename,
            "pages": num_pages,
            "chunks_indexed": n_chunks
        }
    
    def get_document_info(self, doc_id: str) -> dict:
        """Get document information"""
        reg = load_registry()
        if doc_id not in reg:
            raise FileNotFoundError("Document not found")
        
        pdf_path = reg[doc_id]["pdf_path"]
        if not os.path.exists(pdf_path):
            raise FileNotFoundError("PDF file not found")
        
        reader = PdfReader(pdf_path)
        return {
            "doc_id": doc_id,
            "filename": reg[doc_id].get("filename", f"{doc_id}.pdf"),
            "pdf_path": pdf_path,
            "pages": len(reader.pages)
        }
    
    def list_documents(self) -> dict:
        """List all documents in the registry"""
        reg = load_registry()
        
        # Add page count to each document
        enhanced_reg = {}
        for doc_id, doc_info in reg.items():
            enhanced_info = doc_info.copy()
            try:
                if os.path.exists(doc_info["pdf_path"]):
                    reader = PdfReader(doc_info["pdf_path"])
                    enhanced_info["pages"] = len(reader.pages)
                else:
                    enhanced_info["pages"] = 0
                    enhanced_info["status"] = "file_missing"
            except Exception:
                enhanced_info["pages"] = 0
                enhanced_info["status"] = "error"
            
            enhanced_reg[doc_id] = enhanced_info
        
        return enhanced_reg
    
    def query_document(self, doc_id: str, question: str, k: int = 5) -> dict:
        """Query document using RAG"""
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

# Global PDF processor instance
pdf_processor = PDFProcessor()