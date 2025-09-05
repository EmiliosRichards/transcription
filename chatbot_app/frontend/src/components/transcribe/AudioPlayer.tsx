"use client";

import { useState, useRef, useEffect } from 'react';
import { Play, Pause, RotateCcw, RotateCw, Volume2, VolumeX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface AudioPlayerProps {
  src: string;
}

import { useTranscribeStore } from '@/lib/stores/useTranscribeStore';

export function AudioPlayer({ src }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const { seekToTime, setSeekToTime, currentTime, setCurrentTime, setHasPlaybackStarted } = useTranscribeStore();
  const [isPlaying, setIsPlaying] = useState(false);
  const [isSeeking, setIsSeeking] = useState(false);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  // Defer seeks until metadata is available to avoid browser clamping to 0
  const pendingSeekRef = useRef<number | null>(null);
  const resumeAfterSeekRef = useRef<boolean>(false);

  // Ensure audio element starts with correct volume/mute/playback settings
  useEffect(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.volume = volume;
      audio.muted = isMuted;
      audio.playbackRate = playbackRate;
    }
  }, [src]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const clamp = (val: number, min: number, max: number) => Math.min(Math.max(val, min), max);

    const setAudioData = () => {
      const dur = isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
      setDuration(dur);
      // Apply any deferred seek once metadata is known
      if (pendingSeekRef.current !== null) {
        const safeTime = clamp(pendingSeekRef.current, 0, dur || pendingSeekRef.current);
        try {
          audio.currentTime = safeTime;
        } catch (_) {
          // Some browsers might still reject; if so, keep pending
          return;
        }
        setCurrentTime(safeTime);
        pendingSeekRef.current = null;
        if (resumeAfterSeekRef.current) {
          audio.play().catch(() => {});
          setIsPlaying(!audio.paused);
        }
      }
    };

    const setAudioTime = () => {
      // Only sync from audio element when not in the middle of a programmatic jump/drag
      if (!isSeeking) {
        setCurrentTime(audio.currentTime);
      }
    };

    const handleSeeked = () => {
      setIsSeeking(false);
      setCurrentTime(audio.currentTime);
    };

    const handlePlay = () => { setIsPlaying(true); setHasPlaybackStarted(true); };
    const handlePause = () => setIsPlaying(false);
    const handleAudioEnd = () => {
      setIsPlaying(false);
      setCurrentTime(0);
    };

    audio.addEventListener('loadedmetadata', setAudioData);
    audio.addEventListener('loadeddata', setAudioData);
    audio.addEventListener('timeupdate', setAudioTime);
    audio.addEventListener('seeked', handleSeeked);
    audio.addEventListener('play', handlePlay);
    audio.addEventListener('pause', handlePause);
    audio.addEventListener('ended', handleAudioEnd);

    if (audio.readyState >= 1) {
      setAudioData();
    }

    return () => {
      audio.removeEventListener('loadedmetadata', setAudioData);
      audio.removeEventListener('loadeddata', setAudioData);
      audio.removeEventListener('timeupdate', setAudioTime);
      audio.removeEventListener('seeked', handleSeeked);
      audio.removeEventListener('play', handlePlay);
      audio.removeEventListener('pause', handlePause);
      audio.removeEventListener('ended', handleAudioEnd);
    };
  }, [src, setCurrentTime, isSeeking]);

  useEffect(() => {
    const audio = audioRef.current;
    if (seekToTime === null || !audio) return;

    const dur = isFinite(audio.duration) && audio.duration > 0 ? audio.duration : null;
    setIsSeeking(true);

    if (dur === null) {
      // Defer until metadata is loaded
      pendingSeekRef.current = seekToTime;
      // Always autoplay after a transcript segment click
      resumeAfterSeekRef.current = true;
      setCurrentTime(seekToTime);
    } else {
      const safeTime = Math.min(Math.max(seekToTime, 0), dur);
      try {
        audio.currentTime = safeTime;
        setCurrentTime(safeTime);
      } catch (_) {
        pendingSeekRef.current = safeTime;
        resumeAfterSeekRef.current = true;
      }
      // Always play from clicked segment
      audio.play().catch(() => {});
      setIsPlaying(!audio.paused);
      setHasPlaybackStarted(true);
    }
    setSeekToTime(null);
  }, [seekToTime, setSeekToTime, setCurrentTime]);

  const togglePlayPause = () => {
    const audio = audioRef.current;
    if (audio) {
      if (isPlaying) {
        audio.pause();
      } else {
        // Ensure we are not muted inadvertently when starting playback
        if (volume > 0 && audio.muted) {
          audio.muted = false;
          setIsMuted(false);
        }
        audio.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const clamp = (val: number, min: number, max: number) => Math.min(Math.max(val, min), max);

  const handleSeek = (value: number[]) => {
    setIsSeeking(true);
    const requested = value[0];
    const audio = audioRef.current;
    if (!audio) return;
    const dur = isFinite(audio.duration) && audio.duration > 0 ? audio.duration : null;
    if (dur === null) {
      // Defer until metadata available; update UI immediately for responsiveness
      pendingSeekRef.current = requested;
      setCurrentTime(requested);
      return;
    }
    const safeTime = clamp(requested, 0, dur);
    try {
      audio.currentTime = safeTime;
    } catch (_) {
      pendingSeekRef.current = safeTime;
    }
    // Keep UI in sync while seeking
    setCurrentTime(safeTime);
  };

  const handleSeekCommit = () => {
    // Wait for 'seeked' to finalize; just ensure we reflect the latest desired value
    const audio = audioRef.current;
    if (audio) {
      setCurrentTime(audio.currentTime);
    }
  };

  const handlePlaybackRateChange = (rate: number) => {
    const audio = audioRef.current;
    if (audio) {
      audio.playbackRate = rate;
      setPlaybackRate(rate);
    }
  };

  const handleVolumeChange = (value: number[]) => {
    const newVolume = value[0];
    const audio = audioRef.current;
    if (audio) {
      audio.volume = newVolume;
      setVolume(newVolume);
      if (newVolume > 0 && isMuted) {
        setIsMuted(false);
        audio.muted = false;
      } else if (newVolume === 0 && !isMuted) {
        setIsMuted(true);
        audio.muted = true;
      }
    }
  };

  const toggleMute = () => {
    const audio = audioRef.current;
    if (audio) {
      audio.muted = !isMuted;
      setIsMuted(!isMuted);
      if (!isMuted && volume === 0) {
        setVolume(1);
        audio.volume = 1;
      }
    }
  };

  const formatTime = (timeInSeconds: number) => {
    const time = Math.round(timeInSeconds);
    const minutes = Math.floor(time / 60);
    const seconds = time % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  };

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-4xl p-4 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 rounded-lg shadow-2xl z-50">
      <audio ref={audioRef} src={src} key={src} preload="auto" />
      <div className="flex items-center justify-between gap-6">
        {/* Main Controls: Centered */}
        <div className="flex items-center gap-4 flex-grow justify-center">
          <Button onClick={() => {
            const a = audioRef.current; if (!a) return;
            a.currentTime = Math.max(0, a.currentTime - 5);
            setCurrentTime(a.currentTime);
          }} variant="ghost" size="icon" className="text-gray-600 dark:text-gray-400 hover:text-black dark:hover:text-white">
            <RotateCcw size={20} />
          </Button>
          <Button onClick={togglePlayPause} variant="outline" size="icon" className="w-12 h-12 rounded-full bg-white dark:bg-gray-800 shadow-md">
            {isPlaying ? <Pause className="h-6 w-6 text-gray-800 dark:text-gray-200" /> : <Play className="h-6 w-6 text-gray-800 dark:text-gray-200" />}
          </Button>
          <Button onClick={() => {
            const a = audioRef.current; if (!a) return;
            const dur = isFinite(a.duration) && a.duration > 0 ? a.duration : undefined;
            a.currentTime = dur ? Math.min(dur, a.currentTime + 5) : a.currentTime + 5;
            setCurrentTime(a.currentTime);
          }} variant="ghost" size="icon" className="text-gray-600 dark:text-gray-400 hover:text-black dark:hover:text-white">
            <RotateCw size={20} />
          </Button>
        </div>
        {/* Playback Speed and Volume */}
        <div className="flex items-center gap-4">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="w-20 text-xs text-gray-600 dark:text-gray-400">
                {playbackRate}x
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="center">
              {[2.0, 1.9, 1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0].map(rate => (
                <DropdownMenuItem key={rate} onSelect={() => handlePlaybackRateChange(rate)}>
                  {rate.toFixed(1)}x
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <div className="flex items-center gap-2 w-28">
            <Button onClick={toggleMute} variant="ghost" size="icon" className="h-8 w-8 text-gray-600 dark:text-gray-400">
              {isMuted || volume === 0 ? <VolumeX size={18} /> : <Volume2 size={18} />}
            </Button>
            <Slider
              value={[isMuted ? 0 : volume]}
              max={1}
              step={0.05}
              onValueChange={handleVolumeChange}
            />
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4 mt-3">
        <span className="text-xs text-gray-500">{formatTime(currentTime)}</span>
          <Slider
            value={[currentTime]}
            max={duration > 0 ? duration : 100}
            step={1}
            onValueChange={handleSeek}
            onValueCommit={handleSeekCommit}
            onPointerDown={() => setIsSeeking(true)}
            onPointerUp={() => setIsSeeking(false)}
            className="w-full"
            disabled={!(duration > 0)}
          />
        <span className="text-xs text-gray-500">{formatTime(duration)}</span>
      </div>
    </div>
  );
}