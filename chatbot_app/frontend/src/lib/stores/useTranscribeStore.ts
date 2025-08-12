import { create } from 'zustand';

export interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
}

export interface ProcessedTranscriptionSegment extends TranscriptionSegment {
  speaker: string;
}

export interface TranscriptionItem {
  id: number;
  audio_source: string | null;
  created_at: string;
  audio_file_path: string | null;
}

export type ViewMode = 'raw' | 'processed';

export type CinematicStage = 'TRANSCRIBING' | 'PROCESSING' | 'DONE';

interface TranscribeState {
  file: File | null;
  url: string;
  transcription: string;
  transcriptionSegments: TranscriptionSegment[];
  processedTranscriptionSegments: ProcessedTranscriptionSegment[];
  transcriptionId: number | null;
  processedTranscription: string;
  correctedTranscription: string;
  audioUrl: string;
  isLoading: boolean;
  isProcessing: boolean;
  isCorrecting: boolean;
  correctCompanyName: string;
  error: string;
  progress: number;
  progressMessage: string;
  cinematicStage: CinematicStage;
  cinematicMessages: string[];
  history: TranscriptionItem[];
  seekToTime: number | null;
  currentTime: number;
  hasPlaybackStarted: boolean;
  viewMode: ViewMode;
  loadTranscription: (data: any) => void;
  setFile: (file: File | null) => void;
  setUrl: (url: string) => void;
  setTranscription: (transcription: string, segments?: TranscriptionSegment[]) => void;
  setTranscriptionId: (id: number | null) => void;
  setProcessedTranscription: (transcription: string, segments?: ProcessedTranscriptionSegment[]) => void;
  setCorrectedTranscription: (transcription: string) => void;
  setAudioUrl: (url: string) => void;
  fetchAndSetAudioUrl: (id: number) => Promise<void>;
  setIsLoading: (isLoading: boolean) => void;
  setIsProcessing: (isProcessing: boolean) => void;
  setIsCorrecting: (isCorrecting: boolean) => void;
  setCorrectCompanyName: (name: string) => void;
  setError: (error: string) => void;
  startCinematicExperience: () => void;
  advanceCinematicStage: () => void;
  setHistory: (history: TranscriptionItem[]) => void;
  setSeekToTime: (time: number | null) => void;
  setCurrentTime: (time: number) => void;
  setHasPlaybackStarted: (started: boolean) => void;
  setViewMode: (mode: ViewMode) => void;
  reset: () => void;
}

const initialState = {
  file: null,
  url: "",
  transcription: "",
  transcriptionSegments: [],
  processedTranscriptionSegments: [],
  transcriptionId: null,
  processedTranscription: "",
  correctedTranscription: "",
  audioUrl: "",
  isLoading: false,
  isProcessing: false,
  isCorrecting: false,
  correctCompanyName: "",
  error: "",
  progress: 0,
  progressMessage: "",
  cinematicStage: 'DONE' as CinematicStage,
  cinematicMessages: [],
  history: [],
  seekToTime: null,
  currentTime: 0,
  hasPlaybackStarted: false,
  viewMode: 'raw' as ViewMode,
};

export const useTranscribeStore = create<TranscribeState>()((set) => ({
  ...initialState,
  loadTranscription: (data) => set({
    transcriptionId: data.id,
    transcription: data.raw_transcription || "",
    transcriptionSegments: data.raw_segments || [],
    processedTranscription: data.processed_transcription || "",
    processedTranscriptionSegments: data.processed_segments || [],
    correctedTranscription: data.corrected_transcription || "",
    audioUrl: data.audio_file_path ? `/api/audio/${data.id}` : "",
    viewMode: (data.processed_segments && data.processed_segments.length > 0) ? 'processed' : 'raw',
    isLoading: false,
    isProcessing: false,
    error: "",
  }),
  setFile: (file) => set({ file }),
  setUrl: (url) => set({ url }),
  setTranscription: (transcription, segments = []) => set({
    transcription,
    transcriptionSegments: segments,
    // When a new transcription is set, default to raw view
    viewMode: 'raw'
  }),
  setTranscriptionId: (id) => set({ transcriptionId: id }),
  setProcessedTranscription: (transcription, segments = []) => set(state => ({
    processedTranscription: transcription,
    processedTranscriptionSegments: segments,
    // If processed segments are available, switch the view to processed
    viewMode: segments.length > 0 ? 'processed' : state.viewMode
  })),
  setCorrectedTranscription: (transcription) => set({ correctedTranscription: transcription }),
  setAudioUrl: (url) => set({ audioUrl: url }),
  fetchAndSetAudioUrl: async (id: number) => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
      const response = await fetch(`${backendUrl}/api/audio/${id}`, { method: 'GET' });
      if (!response.ok) {
        throw new Error(`Failed to fetch audio file: ${response.statusText}`);
      }

      const contentType = response.headers.get("content-type");

      if (contentType && contentType.includes("application/json")) {
        // Backend indicates cloud storage: use pre-signed URL directly
        const data = await response.json();
        if (data.url) {
          set({ audioUrl: data.url });
        } else {
          throw new Error("Pre-signed URL not found in JSON response.");
        }
      } else {
        // Serve directly from backend endpoint to preserve HTTP Range support
        set({ audioUrl: `${backendUrl}/api/audio/${id}` });
      }
    } catch (error) {
      console.error("Error fetching audio:", error);
      set({ error: "Could not load audio." });
    }
  },
  setIsLoading: (isLoading) => set({ isLoading }),
  setIsProcessing: (isProcessing) => set({ isProcessing }),
  setIsCorrecting: (isCorrecting) => set({ isCorrecting }),
  setCorrectCompanyName: (name) => set({ correctCompanyName: name }),
  setError: (error) => set({ error }),
  startCinematicExperience: () => set({
    isLoading: true,
    error: "",
    transcription: "",
    transcriptionId: null,
    processedTranscription: "",
    audioUrl: "",
    cinematicStage: 'TRANSCRIBING',
    cinematicMessages: [
      "Transcribing with Whisper API...",
      "Timestamping each word...",
    ],
    progress: 5,
    progressMessage: "Uploading and preparing audio...",
  }),
  advanceCinematicStage: () => set(state => {
    if (state.cinematicStage === 'TRANSCRIBING') {
      return {
        cinematicStage: 'PROCESSING',
        cinematicMessages: [
          "Structuring transcript for AI analysis...",
          "Diarizing speakers with advanced model...",
          "Finalizing processed transcript...",
        ],
        // Align with backend's 60% when raw transcript is ready
        progress: 60,
        progressMessage: "Structuring transcript for AI analysis...",
      };
    }
    return {};
  }),
  setHistory: (history) => set({ history }),
  setSeekToTime: (time) => set({ seekToTime: time }),
  setCurrentTime: (time) => set({ currentTime: time }),
  setHasPlaybackStarted: (started) => set({ hasPlaybackStarted: started }),
  setViewMode: (mode) => set({ viewMode: mode }),
  reset: () => set(state => ({
    ...initialState,
    cinematicStage: 'DONE' as CinematicStage,
    // Preserve history across resets
    history: state.history
  })),
}));