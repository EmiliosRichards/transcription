import { create } from 'zustand';

export interface VttCue {
  start: number;
  end: number;
  text: string;
  speaker?: string;
}

interface MediaReviewState {
  videoUrl: string;
  audioUrl: string;
  vttCues: VttCue[];
  docxText: string;
  seekToTime: number | null;
  currentTime: number;
  isPlaying: boolean;
  hasPlaybackStarted: boolean;
  setVideoUrl: (url: string) => void;
  setAudioUrl: (url: string) => void;
  setVttCues: (cues: VttCue[]) => void;
  setDocxText: (text: string) => void;
  setSeekToTime: (time: number | null) => void;
  setCurrentTime: (time: number) => void;
  setIsPlaying: (playing: boolean) => void;
  setHasPlaybackStarted: (started: boolean) => void;
  reset: () => void;
}

const initialState = {
  videoUrl: '',
  audioUrl: '',
  vttCues: [] as VttCue[],
  docxText: '',
  seekToTime: null as number | null,
  currentTime: 0,
  isPlaying: false,
  hasPlaybackStarted: false,
};

export const useMediaReviewStore = create<MediaReviewState>()((set) => ({
  ...initialState,
  setVideoUrl: (url) => set({ videoUrl: url }),
  setAudioUrl: (url) => set({ audioUrl: url }),
  setVttCues: (cues) => set({ vttCues: cues }),
  setDocxText: (text) => set({ docxText: text }),
  setSeekToTime: (time) => set({ seekToTime: time }),
  setCurrentTime: (time) => set({ currentTime: time }),
  setIsPlaying: (playing) => set({ isPlaying: playing }),
  setHasPlaybackStarted: (started) => set({ hasPlaybackStarted: started }),
  reset: () => set({ ...initialState }),
}));


