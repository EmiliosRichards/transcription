# Procfile for Railway deployment
# Note: For monorepo, deploy frontend and backend as separate Railway services

# If deploying backend only:
web: cd chatbot_app/backend && python -m uvicorn main:app --host 0.0.0.0 --port $PORT

# If deploying frontend only:
# web: cd chatbot_app/frontend && npm run start:railway
