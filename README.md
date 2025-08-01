# Full-Stack Transcription and Chatbot POC

This project is a full-stack proof-of-concept application featuring an audio transcription service and an AI-powered chatbot with conversational memory and RAG capabilities.

## Features

- **Audio Transcription:** Upload audio files and transcribe them using the OpenAI Whisper API.
- **AI Chatbot:** Engage in a conversation with an AI assistant that can answer questions based on a knowledge base.
- **Conversational History:** Chat sessions are saved and can be revisited later.
- **Message Deletion:** "Rewind" a conversation by deleting a message and all subsequent messages.
- **Database Integration:** All transcriptions and chat logs are persisted in a PostgreSQL database.
- **Dark/Light Mode:** A theme toggle for user preference.

## Tech Stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Python, SQLAlchemy
- **Database:** PostgreSQL
- **AI:** OpenAI API (Whisper, GPT-4o)

---

## Prerequisites

### System-Level Dependencies

Before you begin, ensure you have the following installed on your system:

- **Python:** Version 3.9 or higher.
- **Node.js:** Version 18 or higher.
- **npm:** Version 9 or higher (usually comes with Node.js).
- **Git:** For cloning the repository and managing versions.
- **C++ Build Tools:** Some Python dependencies, like `chromadb`, may need to be compiled from source.
  - **On Windows:** You can install the "Desktop development with C++" workload via the Visual Studio Installer.
  - **On macOS:** Install the Xcode Command Line Tools by running `xcode-select --install`.
  - **On Debian/Ubuntu:** Install the `build-essential` package by running `sudo apt-get install build-essential`.

### Key Project Dependencies

This project relies on several key libraries to function correctly. The setup scripts will handle their installation, but it's useful to know what they are:

- **Backend:**
  - `FastAPI`: The web framework for building the API.
  - `SQLAlchemy` & `psycopg2-binary`: For connecting to and interacting with the PostgreSQL database.
  - `OpenAI`: The official client for interacting with the OpenAI API for transcription and chat.
  - `ChromaDB`: The vector database used for the Retrieval-Augmented Generation (RAG) functionality.

- **Frontend:**
  - `Next.js` & `React`: The framework and library for building the user interface.
  - `Tailwind CSS`: For styling the application.
  - `Shadcn UI`: Provides the pre-built UI components.

## Setup Instructions

Follow these steps to set up and run the project on a new machine.

### 1. Clone the Repository

First, clone the project repository to your local machine:

```bash
git clone <your-repository-url>
cd <repository-folder>
```

### 2. Backend Setup

The backend is a Python FastAPI application.

#### a. Create a Virtual Environment

It's highly recommended to use a virtual environment to manage Python dependencies.

```bash
# Navigate to the backend directory
cd chatbot_app/backend

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

#### b. Install Dependencies

Install the required Python packages using the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

#### c. Configure Environment Variables

The backend requires a `.env` file to store sensitive information like API keys and database URLs.

1.  In the `chatbot_app/backend` directory, create a new file named `.env`.
2.  Add the following variables to the `.env` file, replacing the placeholder values with your actual credentials:

    ```env
    # .env

    # Your PostgreSQL database connection string
    # Example: postgresql://user:password@host:port/dbname
    DATABASE_URL="your_postgresql_connection_string"

    # Your OpenAI API key
    OPENAI_API_KEY="your_openai_api_key"
    ```

### 3. Frontend Setup

The frontend is a Next.js application.

#### a. Install Dependencies

Navigate to the frontend directory and install the required Node.js packages.

```bash
# From the root directory
cd chatbot_app/frontend

# Install dependencies
npm install
```

The frontend requires a `.env.local` file to connect to the backend API.

1. In the `chatbot_app/frontend` directory, create a new file named `.env.local`.
2. Add the following variable, pointing to your running backend instance:

   ```env
   # .env.local
   NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
   ```

---

## Running the Application

You need to run both the backend and frontend servers simultaneously in separate terminals.

### 1. Run the Backend Server

1.  Open a terminal and navigate to the `chatbot_app/backend` directory.
2.  Make sure your Python virtual environment is activated.
3.  Start the FastAPI server using `uvicorn`.

    ```bash
    python main.py
    ```

    The backend server will typically be available at `http://127.0.0.1:8000`.

### 2. Run the Frontend Server

1.  Open a second terminal and navigate to the `chatbot_app/frontend` directory.
2.  Start the Next.js development server.

    ```bash
    npm run dev
    ```

    The frontend application will be available at `http://localhost:3000`.

You can now open your browser and navigate to `http://localhost:3000` to use the application.
---

## Deployment to Railway

This project is configured for deployment on [Railway](https://railway.app/). The `railway.json` file in the root directory defines the two services (`frontend` and `backend`) and their build and deploy settings.

### 1. Create a Railway Project

1.  Create a new project on Railway and connect it to your GitHub repository.
2.  Railway will automatically detect the `railway.json` file and configure the services.

### 2. Add a PostgreSQL Database

1.  In your Railway project, add a new PostgreSQL database service.
2.  Railway will automatically provide the `DATABASE_URL` environment variable to your backend service.

### 3. Configure Environment Variables

You will need to add your OpenAI API key to the environment variables for the `backend` service in Railway.

1.  Go to your `backend` service settings in Railway.
2.  Add a new environment variable named `OPENAI_API_KEY` and set its value to your OpenAI API key.

### 4. Deploy

Commit and push your changes to your GitHub repository. Railway will automatically build and deploy your application.