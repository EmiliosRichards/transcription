"use client";

import { useState, useRef, useEffect } from 'react';
import { Play, Pause, Rewind, FastForward, Volume2, VolumeX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';

interface AudioPlayerProps {
  src: string;
}

export function AudioPlayer({ src }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [volume, setVolume] = useState(1);
  const [playbackRate, setPlaybackRate] = useState(1);

  useEffect(() => {
    console.log("AudioPlayer mounted or src changed:", src);
    const audio = audioRef.current;
    if (audio) {
      const setAudioData = () => {
        console.log("Audio data loaded");
        setDuration(audio.duration);
        setCurrentTime(audio.currentTime);
      };

      const setAudioTime = () => setCurrentTime(audio.currentTime);

      audio.addEventListener('loadeddata', setAudioData);
      audio.addEventListener('timeupdate', setAudioTime);

      return () => {
        audio.removeEventListener('loadeddata', setAudioData);
        audio.removeEventListener('timeupdate', setAudioTime);
      };
    }
  }, [src]);

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

  const handleSeek = (e: React.MouseEvent<HTMLDivElement, MouseEvent>) => {
    const audio = audioRef.current;
    if (audio) {
      const seekTime = (e.nativeEvent.offsetX / e.currentTarget.offsetWidth) * duration;
      audio.currentTime = seekTime;
      setCurrentTime(seekTime);
    }
  };

  const handlePlaybackRateChange = (rate: number) => {
    const audio = audioRef.current;
    if (audio) {
      audio.playbackRate = rate;
      setPlaybackRate(rate);
    }
  };

  const formatTime = (time: number) => {
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60).toString().padStart(2, '0');
    return `${minutes}:${seconds}`;
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
        <div className="w-full bg-gray-600 h-2 rounded-full cursor-pointer" onClick={handleSeek}>
          <Progress value={(currentTime / duration) * 100} className="h-2" />
        </div>
        <span>{formatTime(duration)}</span>
      </div>
    </div>
  );
}