# Chatbot POC Frontend

This is the Next.js frontend for the Full-Stack Transcription and Chatbot POC. It provides the user interface for interacting with the transcription service and the AI chatbot.

## Features

- **Chat Interface:** A responsive and interactive chat interface for communicating with the AI assistant.
- **Transcription UI:** A user-friendly interface for uploading audio files or providing URLs for transcription.
- **Session History:** A sidebar that displays a list of past chat sessions, allowing users to revisit them.
- **Dark/Light Mode:** A theme toggle for user preference.

## Getting Started

First, ensure the backend server is running. Then, run the development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Environment Variables

The frontend requires a `.env.local` file to connect to the backend API.

1. In the `chatbot_app/frontend` directory, create a new file named `.env.local`.
2. Add the following variable, pointing to your running backend instance:

   ```env
   # .env.local
   NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
