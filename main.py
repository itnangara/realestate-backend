"""
Real Estate Application - FastAPI Backend
Main application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uvicorn
from app.routes import auth, properties, users, applications, favorites, seller, role_routes
from app.utils.database import engine, Base
from app.core.cache import init_cache
from app.core.limiter import limiter
from app.monitoring import setup_metrics
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Real Estate API",
    description="A comprehensive real estate management API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    # Todo: add production live urls
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "*.vercel.app", "*.netlify.app"]
)

# Rate limiter
app.state.limiter = limiter

# Rate limit exception handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"}
    )

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(applications.router, prefix="/api/applications", tags=["Applications"])
app.include_router(favorites.router, prefix="/api/favorites", tags=["Favorites"])
app.include_router(seller.router, prefix="/api/sellers", tags=["Sellers"])
app.include_router(role_routes.router, prefix="/api/roles", tags=["Roles"])

# Setup monitoring and metrics
setup_metrics(app)

@app.on_event("startup")
async def startup_event():
    """Initialize cache on application startup"""
    await init_cache()

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
