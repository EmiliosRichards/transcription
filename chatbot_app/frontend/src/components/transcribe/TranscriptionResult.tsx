"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import ConversationView from "@/components/ConversationView";

interface TranscriptionResultProps {
  transcription: string;
  processedTranscription: string;
  isProcessing: boolean;
  onPostProcess: () => void;
}

export function TranscriptionResult({ transcription, processedTranscription, isProcessing, onPostProcess }: TranscriptionResultProps) {
  if (!transcription && !processedTranscription) {
    return null;
  }

  return (
    <Card className="mt-6">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Transcription Result</CardTitle>
        {transcription && !processedTranscription && (
          <Button
            onClick={onPostProcess}
            disabled={isProcessing}
            className="bg-gradient-to-r from-blue-700 to-blue-500 text-white"
          >
            {isProcessing ? "Processing..." : "Process Transcription"}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {processedTranscription ? (
          <ConversationView transcription={processedTranscription} />
        ) : (
          <p className="whitespace-pre-wrap">{transcription}</p>
        )}
      </CardContent>
    </Card>
  );
}