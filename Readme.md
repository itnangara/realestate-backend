# Start the backend server
opt1: python main.py
opt2: uvicorn main:app --reload

# Real Estate Backend API

Production-ready FastAPI backend for a real estate application with comprehensive property search, user management, role-based access control, and advanced features.

## 🚀 Features

- **Advanced Property Search** - Multi-filter search with JSON features, sorting, pagination
- **User Management** - Authentication, profiles, role-based access control
- **Applications** - Property application management with document handling
- **Favorites** - User favorite properties tracking
- **Sellers** - Seller profile and listing management
- **Roles** - Dynamic role management (buyer, seller, agent, landlord, tenant, investor, admin)
- **Caching** - Redis-based caching for performance
- **Rate Limiting** - Request rate limiting protection
- **Monitoring** - Prometheus metrics and structured logging
- **API Documentation** - Auto-generated OpenAPI/Swagger docs

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [API Documentation](#api-documentation)
- [Docker Deployment](#docker-deployment)
- [Monitoring & Observability](#monitoring--observability)

## 🏃 Quick Start

### Using Docker (Recommended)

```bash
# Start all services (PostgreSQL, Redis, Backend)
docker-compose up -d

# Check logs
docker-compose logs -f server

# Stop services
docker-compose down
```

### Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
1. alembic revision -m "name of migration"
2. ### Edit the migration file
3. alembic upgrade head

# Start server
python main.py
```

## 📦 Installation

### Prerequisites

- Python 3.8+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional)

### Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   .\venv\Scripts\Activate.ps1  # Windows PowerShell
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## ⚙️ Environment Variables

Create a `.env` file in the root directory:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/real_estate_db

# Redis
REDIS_URL=redis://localhost:6379

# JWT
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Application
LOG_LEVEL=INFO
ENVIRONMENT=development
```

## 🗄️ Database Setup

### Using PostgreSQL with Docker

```bash
# Start PostgreSQL
docker run -d \
  --name postgres \
  -e POSTGRES_DB=real_estate_db \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  postgres:15
```

### Run Migrations

```bash
# Apply all migrations
alembic upgrade head

# Rollback to previous version
alembic downgrade -1

# Create new migration
alembic revision --autogenerate -m "description"
```

## 🚀 Running the Application

### Development Mode

```bash
# Option 1: Using Python
python main.py

# Option 2: Using Uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 🧪 Testing

### Run All Tests

```bash
pytest
```

### Run Specific Test Suite

```bash
# Property search tests
pytest tests/properties/ -v

# Authentication tests
pytest tests/auth/ -v

# Full test suite with coverage
pytest --cov=app tests/
```

### Test Coverage Report

```bash
pytest --cov=app --cov-report=html tests/
# Open htmlcov/index.html
```

## 📚 API Documentation

Once the application is running:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Key Endpoints

- `GET /api/properties/search` - Advanced property search with filters
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User authentication
- `GET /api/users/me` - Get current user profile
- `POST /api/applications` - Create property application
- `GET /api/favorites` - Get user favorites

## 🐳 Docker Deployment

### Build and Run

```bash
# Build image
docker build -t real-estate-backend .

# Run container
docker run -p 8000:8000 --env-file .env real-estate-backend
```

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Docker Compose Services

- **Backend**: FastAPI application (Port 8000)
- **PostgreSQL**: Database (Port 5432)
- **Redis**: Cache (Port 6379)

## 📊 Monitoring & Observability

### Prometheus Metrics

Metrics are exposed at: `http://localhost:8000/metrics`

**Available Metrics:**
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency
- `http_errors_total` - Error count

### Logging

Structured logs are written to:
- **File**: `logs/app.log` (rotating, 10MB max)
- **Console**: Standard output

**Log Format:**
```
2024-01-15 10:30:45 - real_estate_app - INFO - property_service.py:123 - Property search executed
```

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "service": "real-estate-api"
}
```

## 🏗️ Project Structure

```
backend/
├── app/
│   ├── core/           # Core utilities (cache, limiter, logger)
│   ├── dependencies/    # FastAPI dependencies
│   ├── models/         # SQLAlchemy models
│   ├── monitoring/      # Prometheus metrics
│   ├── routes/         # API routes
│   ├── schemas/        # Pydantic schemas
│   ├── services/       # Business logic
│   └── utils/          # Utility functions
├── alembic/            # Database migrations
├── tests/              # Test suites
├── docker-compose.yml  # Docker services
├── Dockerfile          # Container image
└── main.py            # Application entry point
```

## 🔒 Security Features

- **JWT Authentication** - Secure token-based auth
- **Password Hashing** - Bcrypt encryption
- **Rate Limiting** - Request throttling
- **CORS** - Cross-origin resource sharing
- **Input Validation** - Pydantic schema validation
- **SQL Injection Protection** - Parameterized queries
- **Whitelist Sorting** - Prevent SQL injection via sort parameters

## 📈 Performance Optimization

- **Redis Caching** - Query result caching
- **Database Indexes** - Optimized search queries
- **JSONB Features** - Fast JSON feature filtering
- **Connection Pooling** - Efficient database connections
- **Pagination** - Limit result sets

## 🛠️ Development

### Code Quality

```bash
# Run linter
flake8 app/

# Format code
black app/
```

### Creating Migrations

```bash
# Auto-generate migration
alembic revision --autogenerate -m "Description"

# Review migration
# Edit alembic/versions/xxx.py

# Apply migration
alembic upgrade head
```

## 📝 License

[Specify your license]

## 👥 Contributors

[List contributors]

## 📞 Support

For issues, questions, or contributions, please open an issue on the repository.

---

**Made with ❤️ using FastAPI**
