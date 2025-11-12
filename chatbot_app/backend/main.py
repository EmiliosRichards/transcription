import uvicorn
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from app.api import router as api_router
from app.services import vector_db
from app.database import create_db_and_tables

# --- Load Environment Variables ---
# This must be done before any other modules are imported that need them.
load_dotenv()

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Application startup...")
    logger.info("Initializing database and tables...")
    await create_db_and_tables()
    logger.info("Database and tables are ready.")
    logger.info("Initializing vector database collection...")
    vector_db.get_or_create_collection()
    logger.info("Vector database collection is ready.")
    yield
    # --- Shutdown ---
    logger.info("Application shutdown...")

# Create FastAPI app instance
app = FastAPI(
    title="Chatbot POC API",
    description="API for the RAG-based chatbot.",
    version="0.1.0",
    lifespan=lifespan
)

# --- CORS Middleware ---
# You can override allowed origins via env var ALLOWED_ORIGINS (comma-separated).
replit_domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5000,http://127.0.0.1:5000"
if replit_domain:
    default_origins += f",https://{replit_domain},http://{replit_domain}"
if railway_domain:
    default_origins += f",https://{railway_domain}"
raw_origins = os.environ.get("ALLOWED_ORIGINS", default_origins).split(",")
allow_origins = [o.strip() for o in raw_origins if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins if allow_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Include API Router ---
app.include_router(api_router, prefix="/api")

# --- Root Endpoint ---
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the Chatbot POC API!"}

# --- Run the app ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)