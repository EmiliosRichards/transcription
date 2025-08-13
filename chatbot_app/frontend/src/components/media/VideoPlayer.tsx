"use client";

import { useEffect, useRef, useState } from 'react';
import { Play, Pause, RotateCcw, RotateCw, Volume2, VolumeX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMediaReviewStore } from '@/lib/stores/useMediaReviewStore';

export default function VideoPlayer({ dense = false, suspend = false, compact = false }: { dense?: boolean; suspend?: boolean; compact?: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const {
    videoUrl,
    audioUrl,
    seekToTime,
    setSeekToTime,
    currentTime,
    setCurrentTime,
    setHasPlaybackStarted,
  } = useMediaReviewStore();

  const [isPlaying, setIsPlaying] = useState(false);
  const [isSeeking, setIsSeeking] = useState(false);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const pendingSeekRef = useRef<number | null>(null);
  const resumeAfterSeekRef = useRef<boolean>(false);
  const [scrubTime, setScrubTime] = useState<number | null>(null);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const computeDuration = (): number => {
      if (isFinite(v.duration) && v.duration > 0) return v.duration;
      if (v.seekable && v.seekable.length > 0) {
        try { return v.seekable.end(v.seekable.length - 1); } catch { /* noop */ }
      }
      return 0;
    };

    const onLoaded = () => {
      const dur = isFinite(v.duration) && v.duration > 0 ? v.duration : 0;
      setDuration(dur);
      if (pendingSeekRef.current !== null) {
        const safe = Math.min(Math.max(pendingSeekRef.current, 0), dur || pendingSeekRef.current);
        try { v.currentTime = safe; } catch {}
        setCurrentTime(safe);
        pendingSeekRef.current = null;
        if (resumeAfterSeekRef.current) {
          v.play().catch(() => {});
          setIsPlaying(!v.paused);
        }
      }
    };
    const onDurationChange = () => {
      const dur = computeDuration();
      if (dur && Math.abs(dur - duration) > 0.5) setDuration(dur);
    };
    const onTimeUpdate = () => { if (!isSeeking) setCurrentTime(v.currentTime); };
    const onPlay = () => { setIsPlaying(true); setHasPlaybackStarted(true); };
    const onPause = () => setIsPlaying(false);
    const onEnded = () => { setIsPlaying(false); setCurrentTime(0); };
    const onSeeked = () => { setIsSeeking(false); setScrubTime(null); setCurrentTime(v.currentTime); };
    const onSeeking = () => { setIsSeeking(true); setScrubTime(v.currentTime); };

    v.addEventListener('loadedmetadata', onLoaded);
    v.addEventListener('loadeddata', onLoaded);
    v.addEventListener('durationchange', onDurationChange);
    v.addEventListener('progress', onDurationChange);
    v.addEventListener('canplay', onDurationChange);
    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('play', onPlay);
    v.addEventListener('pause', onPause);
    v.addEventListener('ended', onEnded);
    v.addEventListener('seeked', onSeeked);
    v.addEventListener('seeking', onSeeking);
    return () => {
      v.removeEventListener('loadedmetadata', onLoaded);
      v.removeEventListener('loadeddata', onLoaded);
      v.removeEventListener('durationchange', onDurationChange);
      v.removeEventListener('progress', onDurationChange);
      v.removeEventListener('canplay', onDurationChange);
      v.removeEventListener('timeupdate', onTimeUpdate);
      v.removeEventListener('play', onPlay);
      v.removeEventListener('pause', onPause);
      v.removeEventListener('ended', onEnded);
      v.removeEventListener('seeked', onSeeked);
      v.removeEventListener('seeking', onSeeking);
    };
  }, [isSeeking, setCurrentTime, setHasPlaybackStarted, duration]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v || seekToTime === null) return;
    const dur = isFinite(v.duration) && v.duration > 0 ? v.duration : null;
    setIsSeeking(true);
    if (dur === null) {
      pendingSeekRef.current = seekToTime;
      resumeAfterSeekRef.current = true;
      setCurrentTime(seekToTime);
    } else {
      const safe = Math.min(Math.max(seekToTime, 0), dur);
      try { v.currentTime = safe; } catch { pendingSeekRef.current = safe; }
      setCurrentTime(safe);
      v.play().catch(() => {});
      setIsPlaying(!v.paused);
      setHasPlaybackStarted(true);
    }
    setSeekToTime(null);
  }, [seekToTime, setSeekToTime, setCurrentTime, setHasPlaybackStarted]);

  // When suspended (during layout transitions), pause playback and hide paint cost
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (suspend) {
      try { v.pause(); } catch {}
      setIsPlaying(false);
    }
  }, [suspend]);

  const togglePlayPause = () => {
    const v = videoRef.current; if (!v) return;
    if (isPlaying) v.pause(); else v.play();
    setIsPlaying(!isPlaying);
  };

  const handleSeek = (value: number[]) => {
    const v = videoRef.current; if (!v) return;
    setIsSeeking(true);
    const requested = value[0];
    const dur = isFinite(v.duration) && v.duration > 0 ? v.duration : null;
    const safe = dur === null ? requested : Math.min(Math.max(requested, 0), dur);
    setScrubTime(safe);
    try { v.currentTime = safe; } catch {}
    // Do not update global currentTime while dragging to avoid transcript re-renders
  };
  const handleSeekCommit = () => {
    const v = videoRef.current; if (!v) { setIsSeeking(false); return; }
    if (scrubTime !== null) {
      try { v.currentTime = scrubTime; } catch {}
    }
    setIsSeeking(false);
    setScrubTime(null);
  };

  const handlePlaybackRateChange = (rate: number) => {
    const v = videoRef.current; if (!v) return;
    v.playbackRate = rate;
    setPlaybackRate(rate);
  };

  const handleVolumeChange = (value: number[]) => {
    const v = videoRef.current; if (!v) return;
    const newVolume = value[0];
    v.volume = newVolume;
    setVolume(newVolume);
    if (newVolume > 0 && isMuted) { v.muted = false; setIsMuted(false); }
    else if (newVolume === 0 && !isMuted) { v.muted = true; setIsMuted(true); }
  };

  const toggleMute = () => {
    const v = videoRef.current; if (!v) return;
    v.muted = !isMuted;
    setIsMuted(!isMuted);
    if (!isMuted && volume === 0) { setVolume(1); v.volume = 1; }
  };

  const formatTime = (timeInSeconds: number) => {
    const t = Math.round(timeInSeconds);
    const m = Math.floor(t / 60);
    const s = t % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const src = videoUrl || audioUrl || null;
  const effectiveDuration = (() => {
    if (duration > 0) return duration;
    const v = videoRef.current;
    if (v) {
      if (isFinite(v.duration) && v.duration > 0) return v.duration;
      if (v.seekable && v.seekable.length > 0) {
        try { return v.seekable.end(v.seekable.length - 1); } catch { /* noop */ }
      }
    }
    return Math.max(scrubTime ?? currentTime, 1);
  })();

  return (
      <div className={`w-full ${dense ? 'pb-6' : 'pb-24'}`}>
      {src ? (
        <div className="w-full rounded-md overflow-hidden bg-black/90">
          <video ref={videoRef} src={src} className={`w-full h-auto ${suspend ? 'invisible' : ''}`} preload="auto" crossOrigin="anonymous" />
        </div>
      ) : (
        <div className="w-full rounded-md border border-dashed border-gray-300 dark:border-gray-700 p-8 text-center text-sm text-gray-500 dark:text-gray-400">
          Load a video or audio file to start playback.
        </div>
      )}
      <div className={`mt-3 p-4 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 rounded-lg shadow ${compact ? 'max-w-[360px] mx-auto' : ''}`}>
        <div className={`${compact ? 'flex flex-col items-center gap-3' : 'flex items-center justify-between gap-6'}` }>
          <div className={`${compact ? 'flex items-center gap-4 justify-center' : 'flex items-center gap-4 flex-grow justify-center'}`}>
            <Button onClick={() => { const v = videoRef.current; if (!v) return; v.currentTime = Math.max(0, v.currentTime - 5); setCurrentTime(v.currentTime); }} variant="ghost" size="icon" className="text-gray-600 dark:text-gray-400 hover:text-black dark:hover:text-white">
              <RotateCcw size={20} />
            </Button>
            <Button onClick={togglePlayPause} variant="outline" size="icon" className="w-12 h-12 rounded-full bg-white dark:bg-gray-800 shadow-md">
              {isPlaying ? <Pause className="h-6 w-6 text-gray-800 dark:text-gray-200" /> : <Play className="h-6 w-6 text-gray-800 dark:text-gray-200" />}
            </Button>
            <Button onClick={() => { const v = videoRef.current; if (!v) return; const dur = isFinite(v.duration) && v.duration > 0 ? v.duration : undefined; v.currentTime = dur ? Math.min(dur, v.currentTime + 5) : v.currentTime + 5; setCurrentTime(v.currentTime); }} variant="ghost" size="icon" className="text-gray-600 dark:text-gray-400 hover:text-black dark:hover:text-white">
              <RotateCw size={20} />
            </Button>
          </div>
          <div className={`${compact ? 'flex items-center gap-3' : 'flex items-center gap-4'}`}>
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
            <div className={`flex items-center gap-2 ${compact ? 'w-24' : 'w-28'}`}>
              <Button onClick={toggleMute} variant="ghost" size="icon" className="h-8 w-8 text-gray-600 dark:text-gray-400">
                {isMuted || volume === 0 ? <VolumeX size={18} /> : <Volume2 size={18} />}
              </Button>
              <Slider value={[isMuted ? 0 : volume]} max={1} step={0.05} onValueChange={handleVolumeChange} />
            </div>
          </div>
        </div>
        <div className={`items-center gap-4 mt-3 ${compact ? 'grid grid-cols-[auto_1fr_auto]' : 'flex'}`}>
          <span className="text-xs text-gray-500">{formatTime(scrubTime ?? currentTime)}</span>
          <Slider
            value={[scrubTime ?? currentTime]}
            max={effectiveDuration}
            min={0}
            step={0.05}
            onValueChange={handleSeek}
            onValueCommit={handleSeekCommit}
            onPointerDown={() => setIsSeeking(true)}
            onPointerUp={() => setIsSeeking(false)}
            className="w-full"
            disabled={!src}
          />
          <span className="text-xs text-gray-500">{formatTime(effectiveDuration)}</span>
        </div>
        
      </div>
    </div>
  );
}


