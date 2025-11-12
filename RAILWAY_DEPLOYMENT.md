# Railway Deployment Guide

This project is configured to work on both Replit and Railway. Here's how to deploy to Railway:

## Architecture

This is a monorepo containing:
- **Frontend**: Next.js 15 app (chatbot_app/frontend/)
- **Backend**: FastAPI Python app (chatbot_app/backend/)

## Deployment Options

### Option 1: Two Separate Services (Recommended)

Deploy frontend and backend as separate Railway services for better scalability:

#### Backend Service
1. Create a new Railway project
2. Add a new service from this GitHub repo
3. Set **Root Directory**: `chatbot_app/backend`
4. Railway will auto-detect Python and use the railway.toml config
5. Add environment variables (see below)
6. Deploy!

#### Frontend Service
1. In the same Railway project, add another service
2. Use the same GitHub repo
3. Set **Root Directory**: `chatbot_app/frontend`
4. Railway will auto-detect Node.js and use the railway.toml config
5. Add environment variables:
   - `NEXT_PUBLIC_API_BASE_URL`: Backend service URL (e.g., https://your-backend.railway.app)
   - `API_BASE_URL_SERVER`: Same as above
6. Deploy!

### Option 2: Single Service (Simpler but less flexible)

Deploy just the backend or frontend individually by setting the root directory.

## Required Environment Variables

### Backend Service
```
DATABASE_URL=postgresql://...  # Railway Postgres or external DB
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
BACKBLAZE_B2_KEY_ID=...
BACKBLAZE_B2_APPLICATION_KEY=...
BACKBLAZE_B2_S3_ENDPOINT=...
BACKBLAZE_B2_BUCKET=...
RAILWAY_PUBLIC_DOMAIN=${RAILWAY_PUBLIC_DOMAIN}  # Auto-set by Railway
PORT=${PORT}  # Auto-set by Railway
```

### Frontend Service
```
NEXT_PUBLIC_API_BASE_URL=https://your-backend-service.railway.app
API_BASE_URL_SERVER=https://your-backend-service.railway.app
RAILWAY_PUBLIC_DOMAIN=${RAILWAY_PUBLIC_DOMAIN}  # Auto-set by Railway
PORT=${PORT}  # Auto-set by Railway
NODE_ENV=production
```

## Database Setup

### Option A: Railway Postgres (Recommended)
1. In your Railway project, add a PostgreSQL database
2. Railway will automatically set `DATABASE_URL` in your backend service
3. Done!

### Option B: External Database
1. Set `DATABASE_URL` environment variable manually
2. Ensure your database is accessible from Railway

## Post-Deployment

1. **Database Migration**: Run migrations if needed
   ```bash
   railway run alembic upgrade head
   ```

2. **Test your deployment**:
   - Backend: `https://your-backend.railway.app/`
   - Frontend: `https://your-frontend.railway.app/`

## Monorepo Deployment Tips

- Railway automatically detects the configuration from `railway.toml` in each directory
- Set the **Root Directory** in Railway service settings to point to the specific app
- Both services can share the same GitHub repo but deploy independently
- Use Railway's environment variable references to connect services

## Differences from Replit

| Feature | Replit | Railway |
|---------|--------|---------|
| Port | 5000 (frontend), 8000 (backend) | Dynamic ($PORT) |
| CORS | REPLIT_DEV_DOMAIN | RAILWAY_PUBLIC_DOMAIN |
| Database | Built-in Replit Postgres | Railway Postgres or external |
| File Storage | /home/runner/workspace | Standard Linux paths |
| Automatic Restart | Replit workflows | Railway restart policies |

## Troubleshooting

### Frontend can't reach backend
- Ensure `NEXT_PUBLIC_API_BASE_URL` points to your Railway backend URL
- Check CORS settings allow Railway domains

### Database connection fails
- Verify `DATABASE_URL` is set correctly
- For Railway Postgres, ensure database service is linked

### Build fails
- Check build logs in Railway dashboard
- Verify all dependencies are in requirements.txt (backend) or package.json (frontend)

### Port binding errors
- Railway sets `$PORT` automatically - don't hardcode it
- The code now uses `${PORT:-5000}` (defaults to 5000 if not set)

## Support

For Railway-specific issues, check:
- Railway Docs: https://docs.railway.app/
- Railway Discord: https://discord.gg/railway

For application issues, check the logs in Railway dashboard.
