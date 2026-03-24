# 🚀 Deployment Checklist for Replit Autoscale

## Required Environment Variables (Secrets)

Before deploying, ensure **ALL** these secrets are configured in your Replit deployment:

### 1. **NextAuth Configuration** (CRITICAL!)
```bash
NEXTAUTH_SECRET="<generate with: openssl rand -base64 32>"
NEXTAUTH_URL="https://your-app-name.replit.app"
```
⚠️ **Without these, authentication will fail with JSON errors!**

### 2. **Azure AD Authentication**
```bash
AZURE_AD_CLIENT_ID="<your-azure-app-client-id>"
AZURE_AD_CLIENT_SECRET="<your-azure-app-secret>"
AZURE_AD_TENANT_ID="<your-azure-tenant-id>"
GROUP_ID_ADMINS="<azure-ad-group-id-for-admins>"
GROUP_ID_USERS="<azure-ad-group-id-for-users>"
```

### 3. **External Database**
```bash
EXTERNAL_DB_HOST="185.216.75.247"
EXTERNAL_DB_DATABASE="<your-db-name>"
EXTERNAL_DB_USER="<your-db-user>"
EXTERNAL_DB_PASSWORD="<your-db-password>"
```

### 4. **Optional Features**
```bash
# Enable guest sign-in (for testing)
ALLOW_GUEST="true"
NEXT_PUBLIC_ALLOW_GUEST="true"

# Dialfire API integration (for campaign mapping)
DIALFIRE_API_TOKEN="<your-dialfire-token>"

# Transcription service
TRANSCRIPTION_API_KEY="<your-transcription-key>"

# Preview environment basic auth (optional)
PREVIEW_BASIC_AUTH="1"
PREVIEW_USER="<username>"
PREVIEW_PASS="<password>"

# Optional: warm backend agents/projects cache to avoid slow "first user" after restarts/idle
WARM_AGENTS_PROJECTS="true"
# Optional startup delay before warming (ms)
WARM_AGENTS_PROJECTS_DELAY_MS="0"
# Optional periodic refresh (minutes). If set, uses ExternalStorage.forceReload() in the background.
WARM_AGENTS_PROJECTS_INTERVAL_MINUTES="60"

# Crewmeister (Time Tracking) integration (optional)
# Used to show Δ Arbeitszeit (Dialfire − Crewmeister) in Multi-Search results.
# Auth is done server-side via POST /api/v3/auth/user/ (Crewmeister API v3).
CREWMEISTER_BASE_URL="https://api.crewmeister.com"
CREWMEISTER_USERNAME="integration-user@your-company.com"
CREWMEISTER_PASSWORD="********"
# Optional: override which duration "type" is summed (default: WORK). Case-insensitive fallback is applied.
CREWMEISTER_WORK_DURATION_TYPE="WORK"
# Optional: if your account uses multiple crews, pin lookups to one crew id (numeric).
# If unset, crewId is resolved from the matched Member record.
CREWMEISTER_CREW_ID="25849"
# Map our agent UUIDs (or normalized agent names) to Crewmeister identity:
# - value can be numeric userId, email, name/username, or explicit prefixes like userId:123 / memberId:456
CREWMEISTER_AGENT_MAP_JSON="{\"<agent-uuid>\":\"123\",\"<agent-uuid-2>\":\"jane.doe@company.com\"}"
# Optional caching TTL (ms)
CREWMEISTER_CACHE_TTL_MS="300000"

# Realtime state duration tracking (optional)
# Tracks how long each agent spends in Dialfire realtime states (inactive/ready/waiting/afterCall/connected)
# and stores daily totals. Recommended: store in DB (requires DATABASE_URL + db:push).
DATABASE_URL="postgres://user:pass@host:5432/dbname"
REALTIME_STATE_STORE="db" # auto|db|external|file
REALTIME_STATE_TRACKING_ENABLED="true"
REALTIME_STATE_TRACKING_INTERVAL_MS="5000"
# Offline gaps > this are treated as 'offwork' (after-hours) instead of 'offline' (in-shift disappearances)
REALTIME_OFFLINE_BREAK_MAX_MS="7200000"
```

---

## Common Deployment Issues & Fixes

### ❌ Issue: "CLIENT_FETCH_ERROR" or "Internal S... is not valid JSON"
**Cause:** Missing `NEXTAUTH_SECRET` or `NEXTAUTH_URL`

**Fix:**
1. Generate secret: `openssl rand -base64 32`
2. Set `NEXTAUTH_SECRET` in deployment secrets
3. Set `NEXTAUTH_URL` to your deployed URL (e.g., `https://your-app.replit.app`)
4. Redeploy

---

### ❌ Issue: Deployment times out waiting for port
**Cause:** Multiple issues can cause this

**Common Fixes:**
1. **Multiple ports in .replit** - Remove all port configs except port 5000
2. **Missing secrets:**
   - `NEXTAUTH_SECRET` (generate with `openssl rand -base64 32`)
   - `NEXTAUTH_URL` (your deployed URL, e.g., `https://your-app.replit.app`)
3. **Shell syntax errors** - Ensure `start-prod.sh` exports env vars before `exec`
4. **Cache warmer timing** - Should delay 90s in production
5. Check deployment logs for specific errors

---

### ❌ Issue: Guest sign-in button doesn't work
**Cause:** Missing environment variables or NextAuth configuration error

**Fix:**
1. Set `ALLOW_GUEST="true"` in deployment secrets
2. Set `NEXT_PUBLIC_ALLOW_GUEST="true"` (with `NEXT_PUBLIC_` prefix!)
3. Ensure `NEXTAUTH_SECRET` is configured
4. Redeploy

---

## 📋 Pre-Deployment Steps

1. ✅ Run `bash build-prod.sh` locally to verify build succeeds
2. ✅ Check all required secrets are set in Replit deployment settings
3. ✅ Verify `NEXTAUTH_URL` matches your actual deployment URL
4. ✅ Generate new `NEXTAUTH_SECRET` if not already set
5. ✅ If using `DATABASE_URL` features: run `npm run db:push` against the deployed database (creates missing tables like `agent_state_durations`)
5. ✅ Click "Deploy" in Replit
6. ✅ Monitor deployment logs for errors
7. ✅ Test authentication after deployment succeeds

---

## 🔍 How to Debug Failed Deployments

1. **Check deployment logs** - Look for specific error messages
2. **Verify secrets** - Make sure ALL required secrets are set
3. **Test locally** - Run `bash start-prod.sh` to test production mode
4. **Check NextAuth** - Most issues are related to missing NEXTAUTH_SECRET/URL
5. **Contact support** - If issue persists, provide deployment logs

---

## ✅ Deployment Success Indicators

- Express backend starts on port 5001
- Next.js starts on port 5000 within 60 seconds
- Health check at `/` responds with 200 OK
- Sign-in page loads without errors
- Guest sign-in works (if enabled)
- Azure AD sign-in redirects correctly

---

**Last Updated:** October 28, 2025
