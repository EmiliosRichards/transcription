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
    fetchAndSetAudioUrl,
    setError,
    correctedTranscription,
    setCorrectedTranscription,
    reset,
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
          await fetchAndSetAudioUrl(Number(id));
        }
      } catch (err: any) {
        setError(err.message);
      }
    };

    if (id) {
      fetchTranscription();
    }

    // Cleanup function to reset the store when the component unmounts
    return () => {
      reset();
    };
  }, [id, setTranscription, setProcessedTranscription, fetchAndSetAudioUrl, setError, backendUrl, setCorrectedTranscription, reset]);

  return (
    <div className="p-6 min-h-screen flex flex-col items-center">
      {/* The AudioPlayer is now fixed, so we don't render it here in the flow */}
      {audioUrl && <AudioPlayer src={audioUrl} />}
      
      <div className="w-full max-w-4xl pb-40"> {/* Added padding-bottom */}
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl text-gray-800 dark:text-white">Transcription Details</h1>
          <div className="flex gap-2">
                         <Link href="/history">
               <Button
                 variant="ghost"
                 className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"
                 size="sm"
               >
                 Back to History
               </Button>
             </Link>
                         <Link href="/transcribe">
               <Button 
                 variant="ghost"
                 size="sm"
                 className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"
               >
                 New Transcription
               </Button>
             </Link>
          </div>
        </div>
        
        <TranscriptionResult />
      </div>
    </div>
  );
}