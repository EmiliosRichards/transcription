import uvicorn
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import router as api_router
from app.services import vector_db
from app.database import create_db_and_tables

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Application startup...")
    logger.info("Initializing database and tables...")
    await create_db_and_tables()
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
# Allow all origins for development purposes.
# For production, you should restrict this to your frontend's domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
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