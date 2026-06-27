from contextlib import asynccontextmanager

from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup: runs once before the app serves traffic ---
    # Later phases initialize shared resources here, e.g.:
    #   app.state.db = await create_db_pool(settings.database_url)
    #   app.state.redis = await create_redis(settings.redis_url)
    print("MiniMart API starting up")
    try:
        yield
        # The app serves requests during the yield.
    finally:
        # --- Shutdown: runs once on a clean stop ---
        #   await app.state.db.close()
        #   await app.state.redis.aclose()
        print("MiniMart API shutting down")


app = FastAPI(title="MiniMart API", version="0.1.0", lifespan=lifespan)

@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Hello, World!"}

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
