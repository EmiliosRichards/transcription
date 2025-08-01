# Architecture & Engineering Standards

This document serves as the single source of truth for all major technical decisions, architectural patterns, and engineering standards for this project. Its purpose is to ensure consistency, quality, and coherence across the entire codebase.

---

## 1. Core Principles

- **Stability Over Features**: We prioritize a stable, reproducible, and well-tested application over rushing to implement new features with unstable dependencies.
- **Asynchronous First (Backend)**: The backend is built on an asynchronous framework (FastAPI). All new I/O-bound operations (database calls, API requests) MUST be asynchronous to avoid blocking the event loop.
- **Configuration is Not Code**: All configurable values (API keys, URLs, model names, file paths, etc.) MUST be managed via environment variables and not hardcoded in the source code.
- **Single Responsibility Principle**: Both frontend and backend components should be small, focused, and responsible for a single piece of functionality. Avoid "God" objects/components.

---

## 2. Technology Stack & Versions

This section will be updated as we progress through the stabilization phase.

### Backend

| Library | Version | Purpose |
|---|---|---|
| Python | `~3.11` | Core language |
| FastAPI | `0.111.0` | Web Framework |
| Pydantic | `2.7.1` | Data validation |
| SQLAlchemy | `2.0.30` | ORM for PostgreSQL |
| asyncpg | `0.29.0` | Async PostgreSQL Driver |
| httpx | `0.25.2` | Async HTTP client |
| openai | `1.30.1` | OpenAI API client |
| uvicorn | `0.29.0` | ASGI server |
| python-dotenv | `1.0.1` | Environment variable management |

### Frontend

| Library | Version | Purpose |
|---|---|---|
| Node.js | `~20.x` | Runtime |
| Next.js | `^15.0.0` | React Framework |
| React | `^19.1.0` | UI Library |
| TypeScript | `^5` | Language |
| Tailwind CSS | `^4.0.0` | CSS Framework |
| Zustand | `^5.0.7` | State Management |

### Data Pipelines

| Library | Version | Purpose |
|---|---|---|
| pandas | `2.2.2` | Data manipulation |
| openai | `1.30.1` | OpenAI API client |
| tqdm | `4.67.1` | Progress bars |

---

## 3. Coding Patterns & Conventions

### Backend

- **API Structure**: Use FastAPI's `APIRouter` to split endpoints into logical, domain-specific files (e.g., `transcription.py`, `chat.py`). Do not place all endpoints in a single `api.py` file.
- **Database Sessions**: Use the dependency injection system to manage database session lifecycles.
- **Error Handling**: Implement standardized error handling and logging for all API endpoints.

### Frontend

- **State Management**: We use `Zustand` for centralized state management to avoid prop drilling and provide a single source of truth for the application state.
- **Component Design**: Components should be small and reusable. Logic should be separated from presentation where possible.
- **Data Fetching**: All data fetching from the backend will be done via a dedicated, typed API client layer. No mock data will be used in production builds.
