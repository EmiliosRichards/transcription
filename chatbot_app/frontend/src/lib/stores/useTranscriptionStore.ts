import { create } from 'zustand';
import { TranscriptionInfo } from '@/lib/types';

interface TranscriptionState {
  transcriptions: TranscriptionInfo[];
  setTranscriptions: (transcriptions: TranscriptionInfo[]) => void;
}

export const useTranscriptionStore = create<TranscriptionState>()((set) => ({
  transcriptions: [],
  setTranscriptions: (transcriptions: TranscriptionInfo[]) => set({ transcriptions }),
}));