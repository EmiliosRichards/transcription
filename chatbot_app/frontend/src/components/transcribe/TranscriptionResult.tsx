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
    hasPlaybackStarted,
    setViewMode,
    isProcessing,
    isLoading,
    transcriptionId,
  } = useTranscribeStore();
  
  const handleSegmentClick = (startTime: number) => {
    setSeekToTime(startTime);
    // If playback hasn't started yet, starting from a segment should begin playback
    if (!hasPlaybackStarted) {
      // flag will be set in AudioPlayer when play event fires
      // nothing else needed here; AudioPlayer reads seekToTime and will call play if paused
    }
  };

  const handleViewChange = (value: string) => {
    if (value === 'raw' || value === 'processed') {
      setViewMode(value as ViewMode);
    }
  };

  const getSpeakerColorClass = (speaker: string) => {
    const speakerUpper = speaker.toUpperCase();
    if (speakerUpper.includes('AGENT')) {
      return "text-white/90";
    }
    if (speakerUpper.includes('DECISION_MAKER')) {
      return "text-green-600 dark:text-green-400";
    }
    return "text-gray-800 dark:text-gray-300"; // Default for 'OTHER' or unknown
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
                        ? "bg-red-200 dark:bg-red-700"
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
            <div className="mt-4 p-4 border rounded-md bg-white dark:bg-gray-900 min-h-[200px] flex flex-col gap-4">
              {processedTranscriptionSegments && processedTranscriptionSegments.length > 0 ? (
                processedTranscriptionSegments.map((segment, index) => {
                  const isAgent = segment.speaker.toUpperCase().includes('AGENT');
                  return (
                    <div
                      key={`processed-${index}`}
                      className={cn(
                        "flex items-end gap-2",
                        isAgent ? "justify-end" : "justify-start"
                      )}
                    >
                      <div
                       className={cn(
                          "max-w-[80%] p-3 rounded-lg cursor-pointer",
                          isAgent
                            ? "bg-blue-500 text-white rounded-br-none"
                            : "bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-bl-none",
                          hasPlaybackStarted && currentTime >= segment.start && currentTime < segment.end
                            ? "ring-2 ring-offset-2 ring-red-500"
                            : ""
                        )}
                        onClick={() => handleSegmentClick(segment.start)}
                      >
                        <div className={cn("font-bold text-sm mb-1", getSpeakerColorClass(segment.speaker))}>
                          {segment.speaker.replace(/\[|\]/g, '')}
                        </div>
                        <p className="text-sm">{segment.text}</p>
                      </div>
                    </div>
                  );
                })
              ) : (
                <p className="text-gray-500 dark:text-gray-400">{processedTranscription || "No processed transcription available."}</p>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}