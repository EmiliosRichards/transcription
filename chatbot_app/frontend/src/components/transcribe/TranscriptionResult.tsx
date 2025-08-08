"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTranscribeStore, ViewMode } from "@/lib/stores/useTranscribeStore";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

export function TranscriptionResult() {
  const {
    transcription,
    transcriptionSegments,
    processedTranscription,
    processedTranscriptionSegments,
    setSeekToTime,
    currentTime,
    viewMode,
    setViewMode,
    isProcessing,
    isLoading,
    transcriptionId,
  } = useTranscribeStore();
  
  const handleSegmentClick = (startTime: number) => {
    setSeekToTime(startTime);
  };

  const handleViewChange = (value: string) => {
    if (value === 'raw' || value === 'processed') {
      setViewMode(value as ViewMode);
    }
  };

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Transcription Result</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs value={viewMode} onValueChange={handleViewChange} className="w-full">
          <TabsList>
            <TabsTrigger value="raw">Raw</TabsTrigger>
            <TabsTrigger value="processed" disabled={processedTranscriptionSegments.length === 0}>
              Processed
            </TabsTrigger>
          </TabsList>
          <TabsContent value="raw">
            <div className="whitespace-pre-wrap mt-4 p-4 border rounded-md bg-gray-50 dark:bg-gray-800 min-h-[200px]">
              {transcriptionSegments && transcriptionSegments.length > 0 ? (
                transcriptionSegments.map((segment, index) => (
                  <span
                    key={`raw-${index}`}
                    onClick={() => handleSegmentClick(segment.start)}
                    className={cn(
                      "cursor-pointer transition-colors duration-200 rounded px-1",
                      currentTime >= segment.start && currentTime < segment.end
                        ? "bg-blue-200 dark:bg-blue-700"
                        : "hover:bg-gray-200 dark:hover:bg-gray-700"
                    )}
                  >
                    {segment.text}{' '}
                  </span>
                ))
              ) : (
                // Fallback for non-segmented raw text
                <p>{transcription}</p>
              )}
            </div>
          </TabsContent>
          <TabsContent value="processed">
            <div className="whitespace-pre-wrap mt-4 p-4 border rounded-md bg-gray-50 dark:bg-gray-800 min-h-[200px]">
              {processedTranscriptionSegments && processedTranscriptionSegments.length > 0 ? (
                processedTranscriptionSegments.map((segment, index) => (
                  <div key={`processed-${index}`} className="mb-2">
                    <span
                      onClick={() => handleSegmentClick(segment.start)}
                      className={cn(
                        "cursor-pointer transition-colors duration-200 px-2 py-1 rounded",
                        currentTime >= segment.start && currentTime < segment.end
                          ? "bg-blue-200 dark:bg-blue-700"
                          : "hover:bg-gray-200 dark:hover:bg-gray-700"
                      )}
                    >
                      <span className="font-bold text-indigo-600 dark:text-indigo-400 mr-2">{segment.speaker}:</span>
                      <span>{segment.text}</span>
                    </span>
                  </div>
                ))
              ) : (
                // Fallback for non-segmented processed text
                <p>{processedTranscription}</p>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}