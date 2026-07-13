from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.categories.router import router as categories_router
from app.core.database import engine
from app.products.router import router as products_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        engine.dispose()
        print("Database connection closed")


app = FastAPI(title="MiniMart API", version="0.1.0", lifespan=lifespan)

app.include_router(categories_router)
app.include_router(products_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Hello, World!"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
