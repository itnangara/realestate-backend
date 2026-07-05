"""
Real Estate Application - FastAPI Backend
Main application entry point
"""

import uuid
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn
from decouple import config
import os
from app.routes import auth, properties, users, favorites, seller, role_routes, documents, webhooks, admin, admin_users, tenant, landlord, maintenance, maintenance_staff, viewings
from app.utils.database import engine, Base
from app.core.cache import init_cache
from app.core.limiter import limiter, init_limiter
from app.core.logger import get_logger
from app.monitoring import setup_metrics
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse


# Initialize structured logger
logger = get_logger(__name__)


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    logger.info("application_starting", version="1.0.0")
    await init_cache()
    logger.info("application_started", version="1.0.0")
    yield
    # Shutdown (if needed in future)
    # logger.info("application_shutting_down")

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Real Estate API",
    description="A comprehensive real estate management API",
    version="1.0.0",
    docs_url="/api/docs" if config("ENVIRONMENT") == "development" else None,
    redoc_url="/api/redoc" if config("ENVIRONMENT") == "development" else None,
    lifespan=lifespan
)

# CORS middleware - get allowed origins from environment
cors_origins = config(
    "CORS_ORIGINS",
    default="http://localhost:3000,http://localhost:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted host middleware - get allowed hosts from environment
trusted_hosts = config(
    "TRUSTED_HOSTS",
    default="localhost,127.0.0.1,*.vercel.app,*.netlify.app"
).split(",")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[host.strip() for host in trusted_hosts]
)

# Rate limiter - initialize with error handling
# If limiter initialization failed, re-initialize and handle gracefully
if limiter is None:
    logger.warning(
        event="rate_limiter_not_available",
        message="Rate limiter not initialized - attempting re-initialization"
    )
    limiter = init_limiter()

if limiter is not None:
    app.state.limiter = limiter
    logger.info(
        event="rate_limiter_attached",
        message="Rate limiter attached to application"
    )
else:
    logger.warning(
        event="rate_limiter_disabled",
        message="Rate limiting disabled - application running without rate limiting protection"
    )
    # Create a dummy limiter state to prevent errors in routes that use @limiter.limit()
    app.state.limiter = None

# Request logging middleware
@app.middleware("http")
async def add_request_logging(request: Request, call_next):
    """
    Clean request/response logging middleware.
    
    Features:
    - Unique request ID for correlation
    - Selective logging (errors, warnings, slow requests)
    - Performance timing
    - User context extraction
    """
    # Generate unique request ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Extract request context
    method = request.method
    path = request.url.path
    
    # Extract user context if available (set by auth dependencies)
    user_id = getattr(request.state, "user_id", None)
    
    # Track request start time
    start_time = time.time()
    
    try:
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Log only errors, warnings, or slow requests (>1 second)
        status_code = response.status_code
        is_slow = duration_ms > 1000
        
        if 400 <= status_code < 500:
            logger.warning(
                event="request_warning",
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration_ms, 2),
                user_id=user_id,
            )
        elif status_code >= 500:
            logger.error(
                event="request_error",
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration_ms, 2),
                user_id=user_id,
            )
        elif is_slow:
            logger.warning(
                event="slow_request",
                request_id=request_id,
                method=method,
                path=path,
                duration_ms=round(duration_ms, 2),
                user_id=user_id,
            )
        
        # Add request ID to response headers for client correlation
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        # Log unhandled exceptions with conditional stack traces
        duration_ms = (time.time() - start_time) * 1000
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        include_stack_trace = log_level == "DEBUG"
        
        log_data = {
            "event": "request_failed",
            "request_id": request_id,
            "method": method,
            "path": path,
            "duration_ms": round(duration_ms, 2),
            "user_id": user_id,
            "error_type": type(e).__name__,
            "error_message": str(e),
        }
        
        # Add stack trace conditionally (for debugging)
        if include_stack_trace:
            log_data["exc_info"] = True
        
        logger.error(**log_data)
        raise


def add_cors_headers(response: JSONResponse, request: Request) -> JSONResponse:
    """
    Add CORS headers to a response.
    
    Exception handlers bypass middleware, so we need to manually add CORS headers.
    This ensures CORS works consistently across all responses, including error responses.
    """
    origin = request.headers.get("origin")
    if origin:
        # Check if origin is in allowed origins (match CORS middleware logic)
        allowed_origins = [o.strip() for o in cors_origins]
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "*"
    return response


# Enterprise-grade user-friendly error message translation
def get_user_friendly_error_message(field_name: str, error_type: str, error_msg: str, field_path: list) -> str:
    """
    Translate technical validation errors into user-friendly messages.
    
    Industry standard: Users see helpful messages, not technical jargon.
    """
    # Field name mapping for better UX
    field_display_names = {
        "employment_status": "Employment Status",
        "employer_name": "Employer Name",
        "job_title": "Job Title",
        "annual_income": "Annual Income",
        "monthly_income": "Monthly Income",
        "credit_score": "Credit Score",
        "bank_name": "Bank Name",
        "bank_account_type": "Bank Account Type",
        "previous_landlord_name": "Previous Landlord Name",
        "previous_landlord_phone": "Previous Landlord Phone",
        "previous_rent_amount": "Previous Rent Amount",
        "rental_history_years": "Rental History (Years)",
        "preferred_lease_duration": "Preferred Lease Duration",
        "max_rent_budget": "Maximum Rent Budget",
        "document_ids": "Documents",
    }
    
    display_name = field_display_names.get(field_name, field_name.replace("_", " ").title())
    
    # Error type to user-friendly message mapping
    if error_type == "missing":
        return f"{display_name} is required"
    elif error_type == "value_error.missing":
        return f"{display_name} is required"
    elif error_type == "type_error.none.not_allowed":
        return f"{display_name} is required"
    elif error_type == "value_error.number.not_gt":
        if "income" in field_name.lower():
            return f"{display_name} must be greater than 0"
        return f"{display_name} must be a positive number"
    elif error_type == "value_error.number.not_ge":
        if "credit_score" in field_name.lower():
            return f"{display_name} must be between 300 and 850"
        return f"{display_name} must be greater than or equal to 0"
    elif error_type == "value_error.str.regex":
        return f"{display_name} format is invalid"
    elif error_type == "value_error.any_str.max_length":
        max_length = error_msg.split("at most")[-1].strip() if "at most" in error_msg else ""
        return f"{display_name} is too long (maximum {max_length} characters)"
    elif error_type == "value_error.any_str.min_length":
        min_length = error_msg.split("at least")[-1].strip() if "at least" in error_msg else ""
        return f"{display_name} is too short (minimum {min_length} characters)"
    elif "greater than" in error_msg.lower() or "ge=" in error_msg.lower():
        return f"{display_name} must be a valid positive number"
    elif "less than" in error_msg.lower() or "le=" in error_msg.lower():
        return f"{display_name} value is too large"
    elif "invalid" in error_msg.lower():
        return f"{display_name} is invalid"
    else:
        # Fallback: capitalize and clean up the original message
        return f"{display_name}: {error_msg.capitalize()}"


# Validation error exception handler (422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Enterprise-grade validation error handler.
    
    Returns structured, user-friendly validation errors that frontend can display
    in a persistent, helpful way (toasts, inline field errors, etc.).
    """
    request_id = getattr(request.state, "request_id", "unknown")
    client_host = request.client.host if request.client else "unknown"
    
    # Extract validation errors in a structured format
    errors = exc.errors()
    field_errors = []
    error_messages = []
    primary_message = None
    
    for error in errors:
        # Get field name (last item in location path)
        field_path = error.get("loc", [])
        field_name = field_path[-1] if field_path else "unknown"
        
        # Get error message and type
        error_msg = error.get("msg", "Validation error")
        error_type = error.get("type", "validation_error")
        
        # Translate to user-friendly message
        user_friendly_msg = get_user_friendly_error_message(field_name, error_type, error_msg, list(field_path))
        
        field_errors.append({
            "field": field_name,
            "message": user_friendly_msg,
            "type": error_type,
            "path": list(field_path)  # Full path for nested fields
        })
        error_messages.append(user_friendly_msg)
    
    # Generate primary message (first error or summary)
    if field_errors:
        primary_message = field_errors[0]["message"]
        if len(field_errors) > 1:
            primary_message = f"{primary_message} and {len(field_errors) - 1} other error(s)"
    
    # Log validation errors with structured logging - include detailed error messages
    # Also print to console for immediate visibility
    # Very useful ***
    error_summary = "; ".join(error_messages)
    print(f"\n❌ VALIDATION ERROR on {request.method} {request.url.path}")
    print(f"   Fields with errors: {', '.join([e['field'] for e in field_errors])}")
    print(f"   Summary: {error_summary}")
    for i, err in enumerate(field_errors, 1):
        print(f"   {i}. {err['field']}: {err['message']} (type: {err['type']})")
    print()
    
    logger.warning(
        event="validation_error",
        request_id=request_id,
        client_ip=client_host,
        method=request.method,
        path=request.url.path,
        field_count=len(field_errors),
        fields=[e["field"] for e in field_errors],
        error_types=[e["type"] for e in field_errors],
        error_messages=[e["message"] for e in field_errors],
        error_summary=error_summary,
        validation_details=field_errors,  # Full error details for debugging
        raw_pydantic_errors=errors,  # Raw Pydantic errors with input values
    )
    
    # Return structured error response with CORS headers
    # Industry standard format: error, message, field-level errors
    response = JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": primary_message or "Please check the form and try again",
            "fields": [e["field"] for e in field_errors],  # Simple list for quick access
            "errors": field_errors,  # Detailed errors with full context for field-level display
            "summary": "; ".join(error_messages),  # Human-readable summary for toast/banner
        },
        headers={"X-Request-ID": request_id}
    )
    return add_cors_headers(response, request)


# Rate limit exception handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceptions with structured logging"""
    request_id = getattr(request.state, "request_id", "unknown")
    client_host = request.client.host if request.client else "unknown"
    
    logger.warning(
        event="rate_limit_exceeded",
        request_id=request_id,
        client_ip=client_host,
        path=request.url.path,
        detail=exc.detail,
    )
    
    response = JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers={"X-Request-ID": request_id}
    )
    return add_cors_headers(response, request)


# Global HTTP exception handler (for 4xx and 5xx errors)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Handle HTTP exceptions with CORS headers.
    
    Supports both simple string details and structured error objects.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # If detail is already a structured dict (from our custom validations), use it directly
    # Otherwise, wrap it in the standard format
    if isinstance(exc.detail, dict):
        content = exc.detail
    else:
        # Simple string detail - convert to structured format
        content = {
            "error": "HTTPException",
            "message": str(exc.detail),
            "status_code": exc.status_code
        }
    
    response = JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers={"X-Request-ID": request_id}
    )
    return add_cors_headers(response, request)


# Global exception handler for unhandled exceptions (500 errors)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with enterprise-grade logging"""
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Determine if we should include stack trace (DEBUG level or ERROR with exc_info)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    include_stack_trace = log_level == "DEBUG"
    
    # Enterprise-grade error logging with conditional stack traces
    log_data = {
        "event": "unhandled_exception",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }
    
    # Add stack trace conditionally (for debugging)
    if include_stack_trace:
        log_data["exc_info"] = True
    
    logger.error(**log_data)
    
    response = JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"X-Request-ID": request_id}
    )
    return add_cors_headers(response, request)

# Applications router: all endpoints use role-scoped routes
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(favorites.router, prefix="/api/favorites", tags=["Favorites"])
app.include_router(seller.router, prefix="/api/sellers", tags=["Sellers"])
app.include_router(role_routes.router, prefix="/api/roles", tags=["Roles"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(admin_users.router, prefix="/api/admin", tags=["Admin - Users"])
app.include_router(tenant.router, prefix="/api", tags=["Tenant"])
app.include_router(landlord.router, prefix="/api", tags=["Landlord"])
from app.routes import lease, lease_sse
app.include_router(lease.router, prefix="/api", tags=["Leases"])
app.include_router(lease_sse.router, prefix="/api", tags=["Leases", "SSE"])
app.include_router(maintenance.router, prefix="/api", tags=["Maintenance"])
app.include_router(maintenance_staff.router, prefix="/api", tags=["Maintenance - Staff"])
app.include_router(viewings.router, prefix="/api", tags=["Viewings"])

# Setup monitoring and metrics
setup_metrics(app)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Real Estate API is running!", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "real-estate-api"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
