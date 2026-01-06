import uuid
import logging
import os
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import tempfile
import hashlib
from typing import Dict, List, Optional
from .logging_config import configure_logging, trace_id_var

try:
    import google.genai.errors as genai_errors
    import google.generativeai as genai
except Exception:
    genai_errors = None
    genai = None

from .graph.workflow import build_workflow
from .schemas import RunResponse, Evidence, Answer, Rule
from . import cache

load_dotenv()

configure_logging()
app = FastAPI(
    title="CLA Evidence Extractor POC",
    description="Extract rules and evidence from PDF documents",
    version="1.0.0"
)
logger = logging.getLogger(__name__)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fail-fast check for GOOGLE_API_KEY
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY environment variable is not set")
logger.info("GOOGLE_API_KEY is set (length: %d)", len(GOOGLE_API_KEY))

# Configure Google GenAI
if genai:
    genai.configure(api_key=GOOGLE_API_KEY)

# Build workflow
workflow = build_workflow()

# Configure static files
BASE_DIR = Path(__file__).resolve().parent.parent  # Goes to apps/api
static_dir = str(BASE_DIR / "static")

# Create static directory if it doesn't exist
os.makedirs(static_dir, exist_ok=True)

print(f"Static directory: {static_dir}")
print(f"Directory exists: {os.path.exists(static_dir)}")

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def add_trace_id_middleware(request: Request, call_next):
    """Add trace ID to each request for logging and debugging"""
    tid = str(uuid.uuid4())
    trace_id_var.set(tid)
    request.state.trace_id = tid
    response = await call_next(request)
    return response


@app.get("/health")
def health():
    """Health check endpoint"""
    return {"ok": True, "service": "CLA Evidence Extractor", "version": "1.0.0"}


@app.get("/")
def root():
    """Redirect root to the demo page"""
    return RedirectResponse(url="/demo")


@app.get("/demo")
def demo_page():
    """Serve the demo HTML"""
    # Check if demo.html exists in static directory
    demo_path = os.path.join(static_dir, "demo.html")
    if os.path.exists(demo_path):
        return RedirectResponse(url="/static/demo.html")
    else:
        # Fallback: serve a simple HTML page
        return HTMLResponse("""
        <html>
            <head>
                <title>CLA Evidence Extractor</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 40px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        text-align: center;
                    }
                    .container {
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 40px;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                    h1 { color: #6ee7b7; }
                    a {
                        color: #60a5fa;
                        text-decoration: none;
                        font-weight: bold;
                    }
                    a:hover { text-decoration: underline; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>CLA Evidence Extractor</h1>
                    <p>Demo page not found. Please ensure demo.html exists in the static directory.</p>
                    <p>Static directory: """ + static_dir + """</p>
                    <p><a href="/static/demo.html">Try direct link to demo.html</a></p>
                    <p><a href="/health">Check API health</a></p>
                </div>
            </body>
        </html>
        """)


@app.get("/api/test")
async def test_endpoint():
    """Test endpoint to verify API is working"""
    return {
        "status": "ok",
        "message": "CLA Evidence Extractor API is running",
        "static_dir": static_dir,
        "static_exists": os.path.exists(static_dir),
        "endpoints": {
            "health": "/health",
            "demo": "/demo",
            "extract": "/extract/overtime",
            "api_test": "/api/test"
        }
    }


def validate_pdf_file(file_path: str, password: str = None) -> dict:
    """
    Validate if a file is a valid PDF

    Args:
        file_path: Path to the file to validate
        password: Optional password for encrypted PDFs

    Returns:
        dict: Validation result
    """
    validation_result = {
        'is_valid': False,
        'is_password_protected': False,
        'error_message': None,
        'page_count': 0,
        'file_size': 0,
        'file_type': 'unknown'
    }

    try:
        # Check if file exists
        if not os.path.exists(file_path):
            validation_result['error_message'] = "File not found"
            return validation_result

        # Check file size
        file_size = os.path.getsize(file_path)
        validation_result['file_size'] = file_size

        if file_size == 0:
            validation_result['error_message'] = "File is empty"
            return validation_result

        # Check file extension
        if not file_path.lower().endswith('.pdf'):
            validation_result['error_message'] = "File must have .pdf extension"
            return validation_result

        # Check PDF header (first 5 bytes should be %PDF-)
        with open(file_path, 'rb') as f:
            header = f.read(5)
            if not header.startswith(b'%PDF-'):
                validation_result['error_message'] = f"Invalid PDF header: {header}"
                return validation_result

        # Try to open with PyPDF2
        try:
            from PyPDF2 import PdfReader
            from PyPDF2.errors import PdfReadError

            with open(file_path, 'rb') as f:
                reader = PdfReader(f)

                # Check if PDF is encrypted/password protected
                if reader.is_encrypted:
                    validation_result['is_password_protected'] = True
                    logger.info(
                        f"PDF is encrypted, attempting decryption with password")

                    # Try to decrypt with provided password
                    if password:
                        try:
                            # Try to decrypt
                            logger.info(
                                f"Decrypting PDF with password length: {len(password)}, repr: {repr(password)}")
                            decrypt_result = reader.decrypt(password)
                            logger.info(f"Decrypt result: {decrypt_result}")

                            # decrypt() returns 0 if password is wrong, 1 if user password matched, 2 if owner password matched
                            if decrypt_result == 0:
                                validation_result['error_message'] = "Incorrect password"
                                logger.error(
                                    "Decrypt result was 0 - password is incorrect")
                            else:
                                # Try to access pages to verify password worked
                                try:
                                    pages = reader.pages
                                    page_count = len(pages)
                                    logger.info(
                                        f"Successfully accessed pages. Page count: {page_count}")
                                    if page_count > 0:
                                        # Password was correct - can read pages
                                        validation_result['is_password_protected'] = False
                                        validation_result['page_count'] = page_count
                                        validation_result['is_valid'] = True
                                        validation_result['file_type'] = 'application/pdf'
                                        logger.info(
                                            "PDF decryption successful!")
                                    else:
                                        validation_result['error_message'] = "PDF has no pages"
                                        logger.warning("PDF has no pages")
                                except Exception as page_err:
                                    # Failed to read pages - wrong password
                                    logger.error(
                                        f"Failed to read pages: {type(page_err).__name__}: {page_err}")
                                    validation_result['error_message'] = "Incorrect password or corrupted PDF"
                        except Exception as decrypt_err:
                            logger.error(
                                f"Decrypt error: {type(decrypt_err).__name__}: {decrypt_err}")
                            validation_result['error_message'] = "Incorrect password or corrupted PDF"
                    else:
                        validation_result['error_message'] = "PDF is password protected"
                        logger.info(
                            "PDF is password protected, no password provided")
                    return validation_result

                # Get page count
                validation_result['page_count'] = len(reader.pages)
                validation_result['is_valid'] = True
                validation_result['file_type'] = 'application/pdf'

        except Exception as e:
            error_msg = str(e).lower()
            if "password" in error_msg or "encrypted" in error_msg:
                validation_result['is_password_protected'] = True
                validation_result['error_message'] = "PDF is password protected"
            else:
                validation_result['error_message'] = f"Invalid PDF structure: {str(e)}"

    except Exception as e:
        validation_result['error_message'] = f"Validation error: {str(e)}"

    return validation_result


def extract_text_from_pdf(pdf_path: str, max_pages: int = 3) -> str:
    """
    Extract text from first few pages of PDF for relevance checking

    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum number of pages to extract (for efficiency)

    Returns:
        str: Extracted text
    """
    try:
        from PyPDF2 import PdfReader

        with open(pdf_path, 'rb') as f:
            reader = PdfReader(f)

            # Extract text from first few pages
            text_parts = []
            pages_to_extract = min(max_pages, len(reader.pages))

            for i in range(pages_to_extract):
                try:
                    page_text = reader.pages[i].extract_text()
                    # Only add if meaningful text
                    if page_text and len(page_text.strip()) > 50:
                        text_parts.append(page_text.strip())
                except Exception as e:
                    logger.warning(f"Error extracting text from page {i}: {e}")

            # Combine text
            extracted_text = "\n\n".join(text_parts)

            # Limit text length for efficiency
            if len(extracted_text) > 3000:
                extracted_text = extracted_text[:3000] + "..."

            return extracted_text

    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return ""


def check_document_relevance(pdf_path: str, question: str) -> Dict:
    """
    Check if the document is relevant to the question using AI

    Args:
        pdf_path: Path to PDF file
        question: User's question

    Returns:
        dict: Relevance check result
    """
    if not genai:
        return {
            'is_relevant': True,  # Skip check if GenAI not available
            'confidence': 0.0,
            'reason': 'GenAI not available, skipping relevance check',
            'document_type': 'unknown'
        }

    try:
        # Extract text from PDF
        extracted_text = extract_text_from_pdf(pdf_path, max_pages=3)

        if not extracted_text or len(extracted_text.strip()) < 100:
            return {
                'is_relevant': False,
                'confidence': 0.0,
                'reason': 'Document contains too little text or cannot be read',
                'document_type': 'unreadable'
            }

        # Prepare prompt for relevance checking
        prompt = f"""
        Analyze the following document content and determine if it's relevant to this question:

        QUESTION: "{question}"

        DOCUMENT CONTENT (first few pages):
        {extracted_text}

        Please analyze and respond with a JSON object containing:
        1. "is_relevant": boolean - whether the document is relevant to the question
        2. "confidence": float between 0-1 - confidence in the relevance assessment
        3. "reason": string - brief explanation of why it is/isn't relevant
        4. "document_type": string - what type of document this appears to be (e.g., "employment_contract", "resume", "invoice", "legal_document", "policy_manual", "other")
        5. "key_topics": array of strings - main topics mentioned in the document

        Focus on whether this document contains information about overtime compensation rules,
        employment policies, labor laws, or related topics. If it appears to be a resume,
        cover letter, invoice, or unrelated document, mark it as not relevant.

        Respond ONLY with valid JSON, no other text.
        """

        # Use Gemini for relevance checking
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)

        try:
            # Extract JSON from response
            response_text = response.text.strip()

            # Clean up response (remove markdown code blocks if present)
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]

            relevance_result = json.loads(response_text)

            # Ensure required fields exist
            if 'is_relevant' not in relevance_result:
                relevance_result['is_relevant'] = False
            if 'confidence' not in relevance_result:
                relevance_result['confidence'] = 0.0
            if 'reason' not in relevance_result:
                relevance_result['reason'] = 'No reason provided'
            if 'document_type' not in relevance_result:
                relevance_result['document_type'] = 'unknown'
            if 'key_topics' not in relevance_result:
                relevance_result['key_topics'] = []

            return relevance_result

        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse relevance check JSON: {e}, Response: {response.text}")
            return {
                'is_relevant': True,  # Default to processing if we can't parse
                'confidence': 0.0,
                'reason': f'Failed to parse AI response: {str(e)}',
                'document_type': 'unknown',
                'key_topics': []
            }

    except Exception as e:
        logger.error(f"Error in relevance check: {e}")
        return {
            'is_relevant': True,  # Default to processing on error
            'confidence': 0.0,
            'reason': f'Error during relevance check: {str(e)}',
            'document_type': 'unknown',
            'key_topics': []
        }


def is_obviously_irrelevant(filename: str, document_type: str, key_topics: List[str]) -> bool:
    """
    Check if document is obviously irrelevant based on filename and type

    Args:
        filename: Original filename
        document_type: AI-detected document type
        key_topics: Key topics from document

    Returns:
        bool: True if obviously irrelevant
    """
    filename_lower = filename.lower()

    # Check filename for obvious non-relevance
    irrelevant_keywords = [
        'resume', 'cv', 'curriculum', 'vitae',
        'invoice', 'receipt', 'bill', 'payment',
        'photo', 'image', 'picture', 'screenshot',
        'menu', 'recipe', 'cookbook',
        'novel', 'fiction', 'story', 'poem',
        'ticket', 'boarding', 'itinerary',
        'certificate', 'diploma', 'degree',
        'brochure', 'flyer', 'advertisement',
        'manual', 'guidebook', 'tutorial'  # Could be relevant if about employment
    ]

    for keyword in irrelevant_keywords:
        if keyword in filename_lower:
            return True

    # Check document type
    irrelevant_types = [
        'resume', 'cv', 'invoice', 'receipt', 'menu',
        'fiction', 'novel', 'ticket', 'certificate',
        'brochure', 'flyer', 'advertisement'
    ]

    if document_type.lower() in irrelevant_types:
        return True

    # Check key topics for obvious irrelevance
    employment_related_keywords = [
        'overtime', 'compensation', 'salary', 'wage', 'pay',
        'employment', 'employee', 'employer', 'work', 'labor',
        'contract', 'agreement', 'policy', 'rule', 'regulation',
        'law', 'legal', 'right', 'benefit', 'hour', 'time',
        'workplace', 'job', 'position', 'duty', 'responsibility'
    ]

    # If none of the key topics are employment-related, it's likely irrelevant
    if key_topics:
        has_employment_topic = any(
            any(emp_keyword in topic.lower()
                for emp_keyword in employment_related_keywords)
            for topic in key_topics
        )
        if not has_employment_topic:
            return True

    return False


@app.post("/extract/overtime", response_model=RunResponse)
async def extract_overtime(
    request: Request,
    pdf: UploadFile = File(...),
    question: str = Form("What are the overtime compensation rules?"),
    password: str = Form(
        None, description="Password for encrypted PDFs (optional)")
):
    """
    Extract rules and evidence from a PDF document

    Args:
        pdf: Uploaded PDF file
        question: Question to ask about the document

    Returns:
        RunResponse: Structured response with rules and evidence
    """
    # Get or generate trace ID
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))

    # Enforce upload size limit (default 10MB)
    max_bytes = int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))
    content_length = request.headers.get("content-length")

    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Uploaded file too large. Maximum size is {max_bytes // (1024*1024)}MB"
                )
        except ValueError:
            pass

    # Validate file extension
    if not pdf.filename or not pdf.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF (.pdf extension)"
        )

    # Stream upload to a temporary file
    suffix = Path(pdf.filename or "uploaded.pdf").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    document_id = pdf.filename or tmp.name

    try:
        # Write uploaded file to temp file
        with tmp as f:
            chunk_size = 64 * 1024  # 64KB chunks
            while True:
                chunk = await pdf.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)

        pdf_path = tmp.name

        # Validate PDF file
        logger.info(
            f"Validating PDF with password: {'*' * len(password) if password else 'None'}")
        validation_result = validate_pdf_file(pdf_path, password=password)
        logger.info(
            f"Validation result: is_valid={validation_result['is_valid']}, is_password_protected={validation_result['is_password_protected']}, error={validation_result['error_message']}")

        if not validation_result['is_valid']:
            # Clean up temp file
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

            error_msg = validation_result['error_message']

            if validation_result['is_password_protected']:
                if not password:
                    raise HTTPException(
                        status_code=400,
                        detail="🔒 This PDF is password protected. Please provide the password to continue."
                    )
                else:
                    # Password was provided but validation still says it's password protected
                    # This means the password was wrong
                    raise HTTPException(
                        status_code=400,
                        detail="❌ Incorrect password or corrupted PDF. Please try again."
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid PDF file: {error_msg}"
                )

        logger.info(
            f"Processing PDF: {document_id}, "
            f"pages: {validation_result['page_count']}, "
            f"size: {validation_result['file_size']} bytes, "
            f"trace_id: {trace_id}"
        )

        # Check document relevance BEFORE processing
        logger.info(f"Checking document relevance for: {document_id}")
        relevance_result = check_document_relevance(pdf_path, question)

        logger.info(
            f"Relevance check result: is_relevant={relevance_result['is_relevant']}, "
            f"confidence={relevance_result['confidence']:.2f}, "
            f"document_type={relevance_result['document_type']}"
        )

        # Check if document is obviously irrelevant
        is_obviously_irrelevant_doc = is_obviously_irrelevant(
            pdf.filename or document_id,
            relevance_result.get('document_type', 'unknown'),
            relevance_result.get('key_topics', [])
        )

        # Determine if we should reject the document
        should_reject = (
            not relevance_result['is_relevant']
            or is_obviously_irrelevant_doc
            or relevance_result.get('document_type') in ['resume', 'cv', 'invoice', 'receipt']
        )

        if should_reject:
            # Clean up temp file
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

            # Build helpful error message
            doc_type = relevance_result.get('document_type', 'unknown')
            reason = relevance_result.get(
                'reason', 'Document not relevant to the question')

            if is_obviously_irrelevant_doc:
                reason = f"Document appears to be a {doc_type}, which is not relevant to overtime compensation rules"

            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Document not relevant",
                    "reason": reason,
                    "document_type": doc_type,
                    "confidence": relevance_result.get('confidence', 0.0),
                    "key_topics": relevance_result.get('key_topics', []),
                    "suggestion": "Please upload a document related to employment policies, labor laws, or compensation rules."
                }
            )

        # Query-level caching
        doc_hash = cache.doc_hash_from_path(pdf_path)
        q_hash = cache.question_hash(question)
        cached = cache.get_query_cache(doc_hash, q_hash)

        if cached:
            cached['trace_id'] = trace_id
            cached['relevance_check'] = relevance_result
            logger.info(
                f"Cache hit for document: {document_id}, question hash: {q_hash}")

            # Clean up temp file
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

            return cached

        # Prepare state for workflow
        state = {
            "pdf_path": pdf_path,
            "document_id": document_id,
            "question": question,
            "trace_id": trace_id,
            "page_count": validation_result['page_count'],
            "file_size": validation_result['file_size'],
            "relevance_check": relevance_result,
            "pdf_password": password
        }

        # Execute workflow
        try:
            result = await workflow.ainvoke(state)
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

            # Handle Google GenAI errors
            if genai_errors is not None and isinstance(e, genai_errors.ClientError):
                logger.error(f"Google GenAI client error: {e}")
                raise HTTPException(
                    status_code=502,
                    detail="Google GenAI authentication/usage error. Please check GOOGLE_API_KEY and API access."
                )

            # Re-raise other errors
            raise

        # Clean up temp file after successful processing
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)

        # Extract answer from workflow result
        agent_json = result.get("agent_json", {})
        answer = agent_json.get("answer") or {"summary": "", "rules": []}

        # Build response
        out = {
            "document_id": document_id,
            "question": question,
            "answer": {
                "summary": answer.get("summary", ""),
                "rules": answer.get("rules", []),
            },
            "evidence": result.get("evidence") or [],
            "citations_by_rule": result.get("citations_by_rule") or {},
            "confidence": float(result.get("confidence", 0.0)),
            "decision": result.get("decision", "needs_human"),
            "missing_info": result.get("missing_info") or [],
            "trace_id": trace_id,
            "relevance_check": relevance_result,
            "metadata": {
                "page_count": validation_result['page_count'],
                "file_size": validation_result['file_size'],
                "processing_time": result.get("processing_time"),
                "document_type": relevance_result.get('document_type', 'unknown')
            }
        }

        # Cache successful auto decisions
        try:
            if out.get('decision') == 'auto':
                cache.set_query_cache(
                    doc_hash, q_hash, out, ttl=60 * 60)  # 1 hour TTL
        except Exception as cache_error:
            logger.warning(f"Failed to cache result: {cache_error}")

        # Return as Pydantic model
        return RunResponse(
            document_id=out['document_id'],
            question=out['question'],
            answer=Answer(
                summary=out['answer']['summary'],
                rules=[Rule(**r) for r in out['answer'].get('rules') or []],
            ),
            evidence=[Evidence(**e) for e in out.get('evidence') or []],
            citations_by_rule=out.get('citations_by_rule') or {},
            confidence=float(out.get('confidence', 0.0)),
            decision=out.get('decision', 'needs_human'),
            missing_info=out.get('missing_info') or [],
            trace_id=out.get('trace_id'),
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Clean up temp file if it exists
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            os.unlink(pdf_path)

        logger.error(
            f"Unexpected error in extract_overtime: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with JSON response"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "trace_id": getattr(request.state, 'trace_id', None)
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "trace_id": getattr(request.state, 'trace_id', None)
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
