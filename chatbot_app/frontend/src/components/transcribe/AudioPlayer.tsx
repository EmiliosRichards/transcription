"use client";

import { useState, useRef, useEffect } from 'react';
import { Play, Pause, Rewind, FastForward } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';

interface AudioPlayerProps {
  src: string;
}

import { useTranscribeStore } from '@/lib/stores/useTranscribeStore';

export function AudioPlayer({ src }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const { seekToTime, setSeekToTime, currentTime, setCurrentTime } = useTranscribeStore();
  const [isPlaying, setIsPlaying] = useState(false);
  const [isSeeking, setIsSeeking] = useState(false);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);

  useEffect(() => {
    const audio = audioRef.current;
    if (audio) {
      const setAudioData = () => {
        setDuration(audio.duration);
        setCurrentTime(audio.currentTime);
      };

      const setAudioTime = () => {
        if (!isSeeking) {
          setCurrentTime(audio.currentTime);
        }
      };

      const handleAudioEnd = () => {
        setIsPlaying(false);
        setCurrentTime(0);
      };

      audio.addEventListener('loadeddata', setAudioData);
      audio.addEventListener('timeupdate', setAudioTime);
      audio.addEventListener('ended', handleAudioEnd);

      // Set initial state in case data is already loaded
      if (audio.readyState >= 2) { // HAVE_CURRENT_DATA
        setAudioData();
      }

      return () => {
        audio.removeEventListener('loadeddata', setAudioData);
        audio.removeEventListener('timeupdate', setAudioTime);
        audio.removeEventListener('ended', handleAudioEnd);
      };
    }
  }, [src, setCurrentTime]);

  useEffect(() => {
    const audio = audioRef.current;
    if (seekToTime !== null && audio) {
      audio.currentTime = seekToTime;
      if (audio.paused) {
        audio.play().then(() => setIsPlaying(true));
      }
      setSeekToTime(null); // Reset after seeking
    }
  }, [seekToTime, setSeekToTime]);

  const togglePlayPause = () => {
    const audio = audioRef.current;
    if (audio) {
      if (isPlaying) {
        audio.pause();
      } else {
        audio.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const handleSeek = (value: number[]) => {
    // Update the UI immediately while dragging
    setCurrentTime(value[0]);
  };

  const handleSeekCommit = (value: number[]) => {
    const audio = audioRef.current;
    if (audio) {
      audio.currentTime = value[0];
    }
    setIsSeeking(false);
  };

  const handlePlaybackRateChange = (rate: number) => {
    const audio = audioRef.current;
    if (audio) {
      audio.playbackRate = rate;
      setPlaybackRate(rate);
    }
  };

  const formatTime = (timeInSeconds: number) => {
    const time = Math.round(timeInSeconds);
    const minutes = Math.floor(time / 60);
    const seconds = time % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  };

  return (
    <div className="w-full p-4 bg-gray-900 text-white rounded-lg">
      <audio ref={audioRef} src={src} key={src} />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button onClick={() => handlePlaybackRateChange(1)} variant={playbackRate === 1 ? "secondary" : "ghost"}>1x</Button>
          <Button onClick={() => handlePlaybackRateChange(1.5)} variant={playbackRate === 1.5 ? "secondary" : "ghost"}>1.5x</Button>
          <Button onClick={() => handlePlaybackRateChange(2)} variant={playbackRate === 2 ? "secondary" : "ghost"}>2x</Button>
        </div>
        <div className="flex items-center gap-4">
          <Button onClick={() => audioRef.current && (audioRef.current.currentTime -= 15)} variant="ghost"><Rewind size={20} /></Button>
          <Button onClick={togglePlayPause} variant="ghost" size="icon" className="bg-white text-black rounded-full">
            {isPlaying ? <Pause size={24} /> : <Play size={24} />}
          </Button>
          <Button onClick={() => audioRef.current && (audioRef.current.currentTime += 15)} variant="ghost"><FastForward size={20} /></Button>
        </div>
        <div />
      </div>
      <div className="flex items-center gap-4 mt-2">
        <span>{formatTime(currentTime)}</span>
        <Slider
          value={[currentTime]}
          max={duration || 100}
          step={1}
          onValueChange={handleSeek}
          onValueCommit={handleSeekCommit}
          onPointerDown={() => setIsSeeking(true)}
          className="w-full"
          disabled={!duration}
        />
        <span>{formatTime(duration)}</span>
      </div>
    </div>
  );
}