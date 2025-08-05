import { create } from 'zustand';

interface TranscribeState {
  file: File | null;
  url: string;
  transcription: string;
  transcriptionId: number | null;
  processedTranscription: string;
  audioUrl: string;
  isLoading: boolean;
  isProcessing: boolean;
  isCorrecting: boolean;
  correctCompanyName: string;
  error: string;
  progress: number;
  progressMessage: string;
  estimatedTime: number | null;
  setFile: (file: File | null) => void;
  setUrl: (url: string) => void;
  setTranscription: (transcription: string) => void;
  setTranscriptionId: (id: number | null) => void;
  setProcessedTranscription: (transcription: string) => void;
  setAudioUrl: (url: string) => void;
  setIsLoading: (isLoading: boolean) => void;
  setIsProcessing: (isProcessing: boolean) => void;
  setIsCorrecting: (isCorrecting: boolean) => void;
  setCorrectCompanyName: (name: string) => void;
  setError: (error: string) => void;
  setProgress: (progress: number, message: string, estimatedTime?: number) => void;
  setProcessingProgress: (progress: number, message: string) => void;
  reset: () => void;
}

const initialState = {
  file: null,
  url: "",
  transcription: "",
  transcriptionId: null,
  processedTranscription: "",
  audioUrl: "",
  isLoading: false,
  isProcessing: false,
  isCorrecting: false,
  correctCompanyName: "",
  error: "",
  progress: 0,
  progressMessage: "",
  estimatedTime: null,
};

export const useTranscribeStore = create<TranscribeState>()((set) => ({
  ...initialState,
  setFile: (file) => set({ file }),
  setUrl: (url) => set({ url }),
  setTranscription: (transcription) => set({ transcription }),
  setTranscriptionId: (id) => set({ transcriptionId: id }),
  setProcessedTranscription: (transcription) => set({ processedTranscription: transcription }),
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
  reset: () => set(initialState),
}));