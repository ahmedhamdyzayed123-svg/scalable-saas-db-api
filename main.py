from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, select
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/saas_db")

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

class TenantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

class TenantCreate(TenantBase):
    api_key: str = Field(..., min_length=16, max_length=64)

class TenantResponse(TenantBase):
    id: int
    api_key: str

    model_config = ConfigDict(from_attributes=True)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(
    title="Scalable SaaS Database & API Architecture",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy", "service": "SaaS Backend API"}

@app.post("/tenants/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(tenant_in: TenantCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TenantModel).where(TenantModel.api_key == tenant_in.api_key))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="API key already registered")
    
    new_tenant = TenantModel(name=tenant_in.name, api_key=tenant_in.api_key)
    db.add(new_tenant)
    await db.commit()
    await db.refresh(new_tenant)
    return new_tenant

@app.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TenantModel).where(TenantModel.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant
