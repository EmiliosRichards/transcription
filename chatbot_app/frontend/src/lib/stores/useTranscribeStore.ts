import { create } from 'zustand';

interface TranscribeState {
  file: File | null;
  url: string;
  transcription: string;
  transcriptionId: number | null;
  processedTranscription: string;
  isLoading: boolean;
  isProcessing: boolean;
  isCorrecting: boolean;
  correctCompanyName: string;
  error: string;
  setFile: (file: File | null) => void;
  setUrl: (url: string) => void;
  setTranscription: (transcription: string) => void;
  setTranscriptionId: (id: number | null) => void;
  setProcessedTranscription: (transcription: string) => void;
  setIsLoading: (isLoading: boolean) => void;
  setIsProcessing: (isProcessing: boolean) => void;
  setIsCorrecting: (isCorrecting: boolean) => void;
  setCorrectCompanyName: (name: string) => void;
  setError: (error: string) => void;
  reset: () => void;
}

export const useTranscribeStore = create<TranscribeState>()((set) => ({
  file: null,
  url: "",
  transcription: "",
  transcriptionId: null,
  processedTranscription: "",
  isLoading: false,
  isProcessing: false,
  isCorrecting: false,
  correctCompanyName: "",
  error: "",
  setFile: (file) => set({ file }),
  setUrl: (url) => set({ url }),
  setTranscription: (transcription) => set({ transcription }),
  setTranscriptionId: (id) => set({ transcriptionId: id }),
  setProcessedTranscription: (transcription) => set({ processedTranscription: transcription }),
  setIsLoading: (isLoading) => set({ isLoading }),
  setIsProcessing: (isProcessing) => set({ isProcessing }),
  setIsCorrecting: (isCorrecting) => set({ isCorrecting }),
  setCorrectCompanyName: (name) => set({ correctCompanyName: name }),
  setError: (error) => set({ error }),
  reset: () => set({
    file: null,
    url: "",
    transcription: "",
    transcriptionId: null,
    processedTranscription: "",
    isLoading: false,
    isProcessing: false,
    isCorrecting: false,
    correctCompanyName: "",
    error: "",
  }),
}));