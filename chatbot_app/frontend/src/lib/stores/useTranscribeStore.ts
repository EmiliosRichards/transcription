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
  estimatedTime: number | null;
  history: TranscriptionItem[];
  seekToTime: number | null;
  currentTime: number;
  viewMode: ViewMode;
  loadTranscription: (data: any) => void; // New action
  setFile: (file: File | null) => void;
  setUrl: (url: string) => void;
  setTranscription: (transcription: string, segments?: TranscriptionSegment[]) => void;
  setTranscriptionId: (id: number | null) => void;
  setProcessedTranscription: (transcription: string, segments?: ProcessedTranscriptionSegment[]) => void;
  setCorrectedTranscription: (transcription: string) => void;
  setAudioUrl: (url: string) => void;
  setIsLoading: (isLoading: boolean) => void;
  setIsProcessing: (isProcessing: boolean) => void;
  setIsCorrecting: (isCorrecting: boolean) => void;
  setCorrectCompanyName: (name: string) => void;
  setError: (error: string) => void;
  setProgress: (progress: number, message: string, estimatedTime?: number) => void;
  setProcessingProgress: (progress: number, message: string) => void;
  setHistory: (history: TranscriptionItem[]) => void;
  setSeekToTime: (time: number | null) => void;
  setCurrentTime: (time: number) => void;
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
  estimatedTime: null,
  history: [],
  seekToTime: null,
  currentTime: 0,
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
  setIsLoading: (isLoading) => set({ isLoading }),
  setIsProcessing: (isProcessing) => set({ isProcessing }),
  setIsCorrecting: (isCorrecting) => set({ isCorrecting }),
  setCorrectCompanyName: (name) => set({ correctCompanyName: name }),
  setError: (error) => set({ error }),
  setProgress: (progress, message, estimatedTime) => set(state => ({
    progress,
    progressMessage: message,
    estimatedTime: estimatedTime ?? state.estimatedTime
  })),
  setProcessingProgress: (progress, message) => set({ progress, progressMessage: message }),
  setHistory: (history) => set({ history }),
  setSeekToTime: (time) => set({ seekToTime: time }),
  setCurrentTime: (time) => set({ currentTime: time }),
  setViewMode: (mode) => set({ viewMode: mode }),
  reset: () => set(state => ({
    ...initialState,
    // Preserve history across resets
    history: state.history
  })),
}));