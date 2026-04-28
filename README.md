# Legal AI Platform - Setup & Run Guide
## 📋 Yêu cầu hệ thống

### Phần mềm bắt buộc:
- **Python 3.10+**
- **Node.js 16+** & **npm/yarn**
- **PostgreSQL 13+**
- **Redis 6+**
- **Ollama** (hoặc LLM service khác)
- **Milvus** hoặc **Qdrant** (Vector DB)
- **Neo4j** (Graph DB - optional)
- **Git**

### Kiểm tra phiên bản:
```bash
python --version          # Python 3.10+
node --version           # Node 16+
npm --version            # npm 8+
psql --version           # PostgreSQL 13+
redis-cli --version      # Redis 6+
```


### 3. Backend setup
```bash
cd backend  # (hoặc từ root: cd project_lightrag/legal_ai_platform/backend)

# Tạo virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\Activate.ps1

# Hoặc macOS/Linux
source venv/bin/activate

# Cài dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head
```

### 4. Frontend setup
```bash
cd frontend
npm install
# hoặc
yarn install
```

### 5. Chạy ứng dụng
```bash
# Terminal 1: Backend (ở folder backend)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend (ở folder frontend)
npm run dev
```

Truy cập: http://localhost:3000


#### 2. Chạy Backend
```bash
cd backend

docker-compose -p legal_ai_platform up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f postgres_db

# Stop
docker-compose down
```
# Development (with reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Frontend Configuration

#### 1. File `frontend/.env` (nếu cần)
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_API_VERSION=v1
```

#### 2. Chạy Frontend
```bash
cd frontend

# Development
npm run dev

# Build production
npm run build

# Preview production build
npm run preview


#### 3. Run migrations
```bash
cd backend
alembic upgrade head



## 🚢 Deployment

### Docker (Development)



## 📄 License

Your License Here

---

**Happy Coding! 🚀**

Nếu có vấn đề, kiểm tra troubleshooting section hoặc liên hệ team.
