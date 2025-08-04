export interface ChatSession {
  session_id: string;
  start_time: string; // The backend sends a datetime object, which will be serialized as a string
  initial_message: string;
}

export interface TranscriptionInfo {
  id: number;
  audio_source: string | null;
  created_at: string;
}