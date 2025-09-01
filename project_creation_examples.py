#!/usr/bin/env python3
"""
Example demonstrating the new project creation functionality
"""
import json

def show_project_creation_examples():
    """Show examples of the new project creation API"""
    
    print("🏗️  NEW PROJECT CREATION API EXAMPLES")
    print("=" * 60)
    
    # Example 1: Create project with PDF upload
    print("1. CREATE PROJECT WITH PDF UPLOAD")
    print("-" * 40)
    print("POST /projects/create")
    print("Content-Type: multipart/form-data")
    print()
    print("Form Data:")
    print("- project_name: 'Office Building Floor Plan'")
    print("- description: 'Main office building architectural plans'") 
    print("- user_id: 1")
    print("- file: floorplan.pdf")
    print()
    
    example_response_with_pdf = {
        "project_id": "a1b2c3d4e5f6g7h8",
        "name": "Office Building Floor Plan",
        "description": "Main office building architectural plans",
        "user_id": 1,
        "document": {
            "doc_id": "x9y8z7w6v5u4t3s2",
            "filename": "floorplan.pdf",
            "pages": 5,
            "chunks_indexed": 42
        },
        "created_at": "just created"
    }
    
    print("Response (200 OK):")
    print(json.dumps(example_response_with_pdf, indent=2))
    
    print("\n" + "=" * 60)
    
    # Example 2: Create project without PDF
    print("2. CREATE PROJECT WITHOUT PDF")
    print("-" * 40)
    print("POST /projects/create")
    print("Content-Type: multipart/form-data")
    print()
    print("Form Data:")
    print("- project_name: 'Residential Complex'")
    print("- description: 'Multi-unit residential building plans'")
    print("- user_id: 1")
    print("- file: (not provided)")
    print()
    
    example_response_without_pdf = {
        "project_id": "p9q8r7s6t5u4v3w2",
        "name": "Residential Complex", 
        "description": "Multi-unit residential building plans",
        "user_id": 1,
        "document": None,
        "created_at": "just created"
    }
    
    print("Response (200 OK):")
    print(json.dumps(example_response_without_pdf, indent=2))
    
    print("\n" + "=" * 60)
    
    # Example 3: Project-aware agent usage
    print("3. PROJECT-AWARE AGENT USAGE")
    print("-" * 40)
    print("POST /agent/project/{project_id}/unified")
    print("Content-Type: multipart/form-data")
    print()
    print("Form Data:")
    print("- user_instruction: 'What is the layout of the kitchen area?'")
    print("- user_id: 1")
    print()
    
    project_agent_response = {
        "response": "The kitchen area features an open-concept design with a large island...",
        "session_id": "session_123",
        "project_id": "a1b2c3d4e5f6g7h8",
        "doc_id": "x9y8z7w6v5u4t3s2",
        "page": 1,
        "type": "information",
        "suggestions": [
            {
                "title": "Dining Area",
                "page": 1,
                "description": "Adjacent dining space layout and seating arrangements."
            },
            {
                "title": "Appliance Details",
                "page": 2,
                "description": "Kitchen appliance specifications and placement."
            }
        ],
        "project_context": {
            "name": "Office Building Floor Plan",
            "description": "Main office building architectural plans"
        }
    }
    
    print("Response (200 OK):")
    print(json.dumps(project_agent_response, indent=2))
    
    print("\n" + "=" * 60)
    
    # Example 4: Get user projects
    print("4. GET USER PROJECTS")
    print("-" * 40)
    print("GET /projects/user/1")
    print()
    
    user_projects_response = {
        "user_id": 1,
        "projects": [
            {
                "project_id": "a1b2c3d4e5f6g7h8",
                "name": "Office Building Floor Plan",
                "description": "Main office building architectural plans",
                "user_id": 1,
                "document": {
                    "doc_id": "x9y8z7w6v5u4t3s2",
                    "filename": "floorplan.pdf",
                    "pdf_path": "/data/docs/x9y8z7w6v5u4t3s2.pdf",
                    "pages": 5
                },
                "created_at": "2024-01-01T10:00:00",
                "updated_at": "2024-01-01T10:00:00"
            },
            {
                "project_id": "p9q8r7s6t5u4v3w2",
                "name": "Residential Complex",
                "description": "Multi-unit residential building plans",
                "user_id": 1,
                "document": None,
                "created_at": "2024-01-01T09:30:00",
                "updated_at": "2024-01-01T09:30:00"
            }
        ]
    }
    
    print("Response (200 OK):")
    print(json.dumps(user_projects_response, indent=2))
    
    print("\n" + "=" * 60)
    print("✅ KEY FEATURES:")
    print("• Single endpoint creates project + uploads PDF")
    print("• Automatic project ID generation")
    print("• Project-aware agent endpoints with context")
    print("• Enhanced responses include project information")
    print("• Full project lifecycle management")
    print("• Backward compatibility with existing document endpoints")

if __name__ == "__main__":
    show_project_creation_examples()