"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import ConversationView from "@/components/ConversationView";
import { Progress } from "@/components/ui/progress";
import { AudioPlayer } from "./AudioPlayer";

interface TranscriptionResultProps {
  transcription: string;
  processedTranscription: string;
  isProcessing: boolean;
  onPostProcess: () => void;
  progress: number;
  progressMessage: string;
  audioUrl?: string;
}

export function TranscriptionResult({
  transcription,
  processedTranscription,
  isProcessing,
  onPostProcess,
  progress,
  progressMessage,
  audioUrl
}: TranscriptionResultProps) {
  if (!transcription && !processedTranscription) {
    return null;
  }

  return (
    <Card className="mt-6">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Transcription Result</CardTitle>
        {transcription && !processedTranscription && !isProcessing && (
          <Button
            onClick={onPostProcess}
            className="bg-gradient-to-r from-blue-700 to-blue-500 text-white"
          >
            Process Transcription
          </Button>
        )}
        {isProcessing && (
          <div className="flex flex-col items-center gap-2 w-1/2">
            <Progress value={progress} />
            <p className="text-sm text-muted-foreground">{progressMessage}</p>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {audioUrl && <AudioPlayer src={audioUrl} />}
        {processedTranscription ? (
          <ConversationView transcription={processedTranscription} />
        ) : (
          <p className="whitespace-pre-wrap mt-4">{transcription}</p>
        )}
      </CardContent>
    </Card>
  );
}