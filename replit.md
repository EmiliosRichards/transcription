# Transcription & Chatbot Application

## Overview
This is a full-stack AI-powered chatbot application with transcription capabilities, migrated from Vercel to Replit. The application consists of:
- **Frontend**: Next.js 15 application with React 19
- **Backend**: FastAPI-based Python API with AI/ML capabilities
- **Database**: PostgreSQL with vector database (ChromaDB) for RAG
- **Storage**: Backblaze B2 for media files

## Recent Changes (Nov 12, 2025)
- ✅ Migrated from Vercel to Replit
- ✅ Configured Next.js to run on port 5000 with 0.0.0.0 binding
- ✅ Updated CORS settings to support Replit domains
- ✅ Installed all frontend and backend dependencies
- ✅ Configured environment variables for production use
- ✅ Both frontend and backend workflows running successfully
- ✅ Fixed serverActions.allowedOrigins security issue
- ✅ Fixed fusion page API calls to use Next.js proxy (relative URLs)
- ✅ Fixed backend blocking issue - subprocess calls now run in threads
- ✅ Fixed UI flickering during long-running fusion tasks
- ✅ Cleaned up 4GB of disk space (temporary files)
- ✅ Added Railway deployment compatibility (multi-platform support)

## Project Architecture

### Frontend (`chatbot_app/frontend/`)
- **Framework**: Next.js 15 with App Router
- **UI**: React 19 with Tailwind CSS and Radix UI components
- **State Management**: Zustand
- **Features**:
  - Chat interface with streaming responses
  - Audio/video transcription upload
  - Media review and analysis
  - Dashboard with analytics
  - Conversation history

### Backend (`chatbot_app/backend/`)
- **Framework**: FastAPI with async/await support
- **AI/ML**: OpenAI GPT-4, Google AI, Mistral AI
- **Database**: PostgreSQL (SQLAlchemy ORM) + ChromaDB for vectors
- **Features**:
  - RAG-based chatbot
  - Audio transcription (Whisper)
  - Diarization and speaker detection
  - Media processing pipeline
  - B2 cloud storage integration

## Environment Variables

Required secrets (already configured):
- `DATABASE_URL` - PostgreSQL connection string
- `OPENAI_API_KEY` - OpenAI API key for GPT models
- `GOOGLE_API_KEY` - Google AI API key
- `BACKBLAZE_B2_KEY_ID` - B2 storage key ID
- `BACKBLAZE_B2_APPLICATION_KEY` - B2 application key
- `BACKBLAZE_B2_S3_ENDPOINT` - B2 S3 endpoint URL
- `BACKBLAZE_B2_BUCKET` - B2 bucket name

Optional configuration:
- `ALLOWED_ORIGINS` - CORS allowed origins (auto-configured for Replit)
- `MAIN_LLM_MODEL` - Primary LLM model (default: gpt-4o)
- `EMBEDDING_MODEL` - Embedding model (default: text-embedding-3-small)
- `TRANSCRIPTION_MODEL` - Transcription model (default: whisper-1)

## Running the Application

### Automatic Startup (Recommended)
Both frontend and backend run automatically via configured workflows:
- **Frontend**: Next.js on port 5000 (webview)
- **Backend**: FastAPI on port 8000 (console output)

Access your application at the Replit webview URL.

### Manual Backend Start (Alternative)
If you need to restart the backend manually:
```bash
cd chatbot_app/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
Or use the startup script:
```bash
./chatbot_app/backend/start.sh
```

## Key Files & Directories

### Configuration
- `chatbot_app/frontend/next.config.ts` - Next.js config (Replit-optimized)
- `chatbot_app/frontend/package.json` - Frontend dependencies
- `chatbot_app/backend/requirements.txt` - Backend dependencies
- `chatbot_app/backend/app/config.py` - Backend configuration

### Important Directories
- `chatbot_app/frontend/src/app/` - Next.js app routes
- `chatbot_app/frontend/src/components/` - React components
- `chatbot_app/backend/app/routers/` - API endpoints
- `chatbot_app/backend/app/services/` - Business logic
- `chatbot_app/backend/app/prompts/` - AI prompts

## Development Notes

### Port Configuration
- Frontend: **Port 5000** (required for Replit webview)
- Backend: **Port 8000** (internal)
- Both bind to `0.0.0.0` for Replit compatibility

### CORS & Security
- CORS automatically configured for Replit domains
- Cross-origin requests handled via Next.js rewrites
- API keys stored securely in Replit Secrets

### Known Limitations
- WhisperX dependency skipped (not critical for basic functionality)

## Deployment Options

This project supports deployment to multiple platforms:

### Replit (Current Environment)
- Already configured and running
- Automatic workflows for frontend and backend
- Built-in database and secrets management
- Port 5000 (frontend), Port 8000 (backend)

### Railway
- Full Railway compatibility added
- Dynamic port binding support
- See `RAILWAY_DEPLOYMENT.md` for detailed deployment guide
- Deploy frontend and backend as separate services
- Supports Railway Postgres or external databases
- Configuration files:
  - `railway.toml` - Root monorepo config
  - `chatbot_app/frontend/railway.toml` - Frontend service config
  - `chatbot_app/backend/railway.toml` - Backend service config
  - `Procfile` - Alternative deployment method

### Key Multi-Platform Features
- Dynamic PORT environment variable support (defaults to 5000 for Replit)
- Auto-detection of platform-specific domains (REPLIT_DEV_DOMAIN, RAILWAY_PUBLIC_DOMAIN)
- Platform-agnostic CORS configuration
- Environment-based configuration (no hardcoded values)

## User Preferences
- None specified yet

## Next Steps
1. Run database migrations if needed: `cd chatbot_app/backend && alembic upgrade head`
2. Test media upload and transcription functionality
3. Verify RAG chatbot responses with your data
4. Configure additional AI models if desired
5. (Optional) Deploy to Railway - see `RAILWAY_DEPLOYMENT.md`
