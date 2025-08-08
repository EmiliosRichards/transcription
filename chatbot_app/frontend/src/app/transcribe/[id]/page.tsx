"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useTranscribeStore } from "@/lib/stores/useTranscribeStore";
import { TranscriptionResult } from "@/components/transcribe/TranscriptionResult";
import { AudioPlayer } from "@/components/transcribe/AudioPlayer";
import { useParams } from "next/navigation";

export default function TranscriptionDetailPage() {
  const params = useParams();
  const {
    transcription,
    processedTranscription,
    audioUrl,
    setTranscription,
    setProcessedTranscription,
    setAudioUrl,
    setError,
    correctedTranscription,
    setCorrectedTranscription,
  } = useTranscribeStore();
  
  const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const id = params.id as string;

  useEffect(() => {
    const fetchTranscription = async () => {
      try {
        const response = await fetch(`${backendUrl}/api/transcriptions/${id}`);
        if (!response.ok) {
          const err = await response.json();
          throw new Error(err.detail || "Failed to fetch transcription details.");
        }
        const data = await response.json();
        setTranscription(data.raw_transcription || "", data.raw_segments || []);
        setProcessedTranscription(data.processed_transcription || "", data.processed_segments || []);
        setCorrectedTranscription(data.corrected_transcription || "");
        if (data.audio_file_path) {
          setAudioUrl(`${backendUrl}/api/audio/${id}`);
        }
      } catch (err: any) {
        setError(err.message);
      }
    };

    if (id) {
      fetchTranscription();
    }
  }, [id, setTranscription, setProcessedTranscription, setAudioUrl, setError, backendUrl, setCorrectedTranscription, id]);

  return (
    <div className="p-6 min-h-screen flex flex-col items-center">
      <div className="w-full max-w-4xl">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl text-gray-800 dark:text-white">Transcription Details</h1>
          <div className="flex gap-2">
            <Link href="/history">
              <Button variant="outline">Back to History</Button>
            </Link>
            <Link href="/transcribe">
              <Button>New Transcription</Button>
            </Link>
          </div>
        </div>
        
        {audioUrl && (
          <div className="mb-6">
            <AudioPlayer src={audioUrl} />
          </div>
        )}

        <TranscriptionResult />
      </div>
    </div>
  );
}