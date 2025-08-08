"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTranscribeStore } from "@/lib/stores/useTranscribeStore";
import { useTranscribeApi } from "@/lib/hooks/useTranscribeApi";
import { AudioPlayer } from "@/components/transcribe/AudioPlayer";
import Link from "next/link";
import { PlayCircle } from "lucide-react";
import { TranscriptionItem } from "@/lib/stores/useTranscribeStore";

export default function HistoryPage() {
  const { history, audioUrl, setAudioUrl } = useTranscribeStore();
  const { getHistory } = useTranscribeApi();

  useEffect(() => {
    getHistory();
  }, [getHistory]);

  const handlePlayAudio = (transcriptionId: number) => {
    const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
    setAudioUrl(`${backendUrl}/api/audio/${transcriptionId}`);
  };

  return (
    <div className="p-6 min-h-screen flex flex-col items-center">
      <div className="w-full max-w-6xl">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl text-gray-800 dark:text-white">Transcription History</h1>
          <Link href="/transcribe">
            <Button>New Transcription</Button>
          </Link>
        </div>
        {audioUrl && (
          <div className="mb-6">
            <AudioPlayer src={audioUrl} />
          </div>
        )}
        <Card>
          <CardHeader>
            <CardTitle>Past Transcriptions</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((item: TranscriptionItem) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.id}</TableCell>
                    <TableCell className="max-w-xs truncate">{item.audio_source}</TableCell>
                    <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                    <TableCell className="text-right">
                      {item.audio_file_path && (
                        <Button variant="ghost" size="icon" onClick={() => handlePlayAudio(item.id)}>
                          <PlayCircle className="h-5 w-5" />
                        </Button>
                      )}
                      <Link href={`/transcribe/${item.id}`}>
                        <Button variant="outline" size="sm">View Details</Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}