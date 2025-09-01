# Floor Plan Agent API - Modularized Architecture

## Overview
This is a modularized version of the Floor Plan Agent API that provides AI-powered document analysis and annotation capabilities. The application has been reorganized into a clean, maintainable modular structure.

## Architecture

### Module Structure
```
modules/
├── config/          # Configuration and utilities
│   ├── settings.py  # Application settings and environment variables
│   ├── utils.py     # Utility functions
│   └── __init__.py
├── database/        # Database models and operations
│   ├── models.py    # User and chat message models, database operations
│   └── __init__.py
├── auth/           # Authentication services
│   ├── service.py   # Authentication business logic
│   ├── endpoints.py # Authentication API endpoints
│   └── __init__.py
├── pdf_processing/ # PDF processing and RAG
│   ├── service.py   # PDF indexing and RAG services
│   ├── endpoints.py # Document management API endpoints
│   └── __init__.py
├── agent/          # AI agent workflow
│   ├── tools.py     # LangChain tools for floor plan processing
│   ├── workflow.py  # Agent workflow and memory management
│   └── __init__.py
├── api/            # API endpoints
│   ├── agent_endpoints.py    # Unified agent and chat endpoints
│   ├── general_endpoints.py  # General utility endpoints
│   └── __init__.py
└── __init__.py
```

## Key Features

### 1. Enhanced Authentication System
- **Regular Signup/Login**: Uses firstname, lastname, email, password with validation
- **Google OAuth**: Secure Google sign-in/sign-up integration
- **Password Security**: Minimum length requirements and secure hashing

### 2. Unified Workflow System
- **Intelligent Intent Detection**: AI agent automatically determines whether user wants:
  - Question answering (RAG) about document content with **topic suggestions**
  - Floor plan annotation/marking
- **Enhanced RAG with Suggestions**: When answering questions, the system now provides:
  - Comprehensive answer to the user's question
  - Related topic suggestions with page numbers
  - Topic descriptions to help users explore further
- **Single Endpoint**: `/agent/unified` handles both workflows seamlessly
- **Chat Interface**: Conversational interface with session management

### 3. Modular Design Benefits
- **Separation of Concerns**: Each module handles specific functionality
- **Maintainability**: Easy to update individual components
- **Testability**: Each module can be tested independently
- **Scalability**: Easy to add new features or modify existing ones
