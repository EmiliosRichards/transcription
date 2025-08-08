"use client";

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useTranscribeStore } from '@/lib/stores/useTranscribeStore';
import { AudioPlayer } from '@/components/transcribe/AudioPlayer';
import { TranscriptionResult } from '@/components/transcribe/TranscriptionResult';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export default function TranscriptionViewerPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const { loadTranscription, isLoading, error, setError, audioUrl } = useTranscribeStore();

  useEffect(() => {
    async function fetchAndLoadTranscription() {
      if (!id) return;
      try {
        const response = await fetch(`/api/transcriptions/${id}`);
        if (!response.ok) {
          throw new Error('Failed to fetch transcription');
        }
        const fetchedData = await response.json();
        loadTranscription(fetchedData);
      } catch (err: any) {
        setError(err.message);
      }
    }
    fetchAndLoadTranscription();
  }, [id, loadTranscription, setError]);

  async function handleDelete() {
    if (!id) return;
    try {
      const response = await fetch(`/api/transcriptions/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error('Failed to delete transcription');
      }
      router.push('/history');
    } catch (err: any) {
      setError(err.message);
    }
  }

  // The handleProcess function can be re-implemented here if needed,
  // but it's removed for now to simplify the UI unification.

  return (
    <div className="container mx-auto p-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Transcription Details (ID: {id})</CardTitle>
          <div className="flex items-center space-x-2">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive">Delete</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This action cannot be undone. This will permanently delete the
                    transcription and all of its associated data.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete}>Continue</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            <Link href="/history">
              <Button variant="outline">Back to History</Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading && <p>Loading...</p>}
          {error && <p className="text-red-500">Error: {error}</p>}
          {!isLoading && !error && (
            <>
              {audioUrl && <AudioPlayer src={audioUrl} />}
              <TranscriptionResult />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}