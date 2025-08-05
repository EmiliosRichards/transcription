"use client";

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import ConversationView from '@/components/ConversationView';

interface TranscriptionData {
  raw_transcription: string | null;
  processed_transcription: string | null;
  corrected_transcription: string | null;
}

export default function TranscriptionViewerPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [data, setData] = useState<TranscriptionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState<string | null>(null);
  const [processingProgress, setProcessingProgress] = useState(0);

  async function fetchTranscription() {
    if (!id) return;
    try {
      setLoading(true);
      const response = await fetch(`/api/transcriptions/${id}`);
      if (!response.ok) {
        throw new Error('Failed to fetch transcription');
      }
      const fetchedData = await response.json();
      setData(fetchedData);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchTranscription();
  }, [id]);

  const finalTranscript = data?.corrected_transcription || data?.processed_transcription;

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

  async function handleProcess() {
    if (!id) return;
    setIsProcessing(true);
    setProcessingStatus("Starting post-processing...");
    setError(null);

    try {
      const response = await fetch('/api/post-process-transcription', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcription_id: parseInt(id) }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start processing task');
      }

      const { task_id } = await response.json();

      // Poll for status
      const interval = setInterval(async () => {
        try {
          const statusResponse = await fetch(`/api/transcribe/status/${task_id}`);
          if (!statusResponse.ok) {
            // If the task is not found, it might have been cleaned up.
            // We assume it's done and stop polling.
            if (statusResponse.status === 404) {
              setProcessingStatus("Task completed and status cleared.");
              clearInterval(interval);
              setIsProcessing(false);
              fetchTranscription(); // Re-fetch data to show the processed transcript
              return;
            }
            throw new Error('Failed to get task status');
          }

          const statusData = await statusResponse.json();
          setProcessingStatus(statusData.message);
          setProcessingProgress(statusData.progress);

          if (statusData.status === 'SUCCESS') {
            clearInterval(interval);
            setIsProcessing(false);
            setProcessingStatus("Processing complete!");
            fetchTranscription(); // Re-fetch data
          } else if (statusData.status === 'ERROR') {
            clearInterval(interval);
            setIsProcessing(false);
            setError(statusData.result || 'An unknown error occurred during processing.');
          }
        } catch (pollError: any) {
          clearInterval(interval);
          setIsProcessing(false);
          setError(pollError.message);
        }
      }, 2000);

    } catch (err: any) {
      setIsProcessing(false);
      setError(err.message);
    }
  }

  return (
    <div className="container mx-auto p-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Transcription Details (ID: {id})</CardTitle>
          <div className="flex items-center space-x-2">
            {data?.raw_transcription && !finalTranscript && !isProcessing && (
              <Button onClick={handleProcess}>Process Transcription</Button>
            )}
            {finalTranscript && !isProcessing && (
              <Button onClick={handleProcess} variant="secondary">Re-process Transcript</Button>
            )}
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
          {loading && <p>Loading...</p>}
          {error && <p className="text-red-500">Error: {error}</p>}
          {isProcessing && (
            <div className="my-4">
              <p>{processingStatus}</p>
              <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700 mt-2">
                <div className="bg-blue-600 h-2.5 rounded-full" style={{ width: `${processingProgress}%` }}></div>
              </div>
            </div>
          )}
          {data && (
            <Tabs defaultValue="raw" className="w-full">
              <TabsList>
                {data.raw_transcription && <TabsTrigger value="raw">Raw Transcription</TabsTrigger>}
                {finalTranscript && <TabsTrigger value="final">Final Transcript</TabsTrigger>}
              </TabsList>
              {data.raw_transcription && (
                <TabsContent value="raw">
                  <div className="prose dark:prose-invert max-w-none p-4 border rounded-md">
                    <p className="whitespace-pre-wrap">{data.raw_transcription}</p>
                  </div>
                </TabsContent>
              )}
              {finalTranscript && (
                <TabsContent value="final">
                  <div className="prose dark:prose-invert max-w-none p-4 border rounded-md">
                    <ConversationView transcription={finalTranscript} />
                  </div>
                </TabsContent>
              )}
            </Tabs>
          )}
        </CardContent>
      </Card>
    </div>
  );
}