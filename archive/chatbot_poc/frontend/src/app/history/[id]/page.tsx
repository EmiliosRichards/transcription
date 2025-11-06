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
  const id = params.id;

  const [data, setData] = useState<TranscriptionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      async function fetchTranscription() {
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

      fetchTranscription();
    }
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
          {loading && <p>Loading...</p>}
          {error && <p className="text-red-500">Error: {error}</p>}
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