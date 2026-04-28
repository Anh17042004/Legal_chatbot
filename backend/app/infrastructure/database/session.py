from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False, # Tắt echo để không in SQL ra log
    pool_size=20,  # Số kết nối tối đa luôn mở
    max_overflow=10, # Số kết nối khẩn cấp tạo thêm
    pool_pre_ping=True, # Kiểm tra kết nối trước khi dùng
    pool_recycle=3600, # Tự động ngắt kết nối sau 1 giờ
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False, # Không tự động update session khi DB thay đổi
    autoflush=False, # Không tự động save khi có thay đổi
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
