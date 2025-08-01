"use client";

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Trash2 } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface TranscriptionInfo {
  id: number;
  audio_source: string | null;
  created_at: string;
}

export default function HistoryPage() {
  const [transcriptions, setTranscriptions] = useState<TranscriptionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function fetchTranscriptions() {
    try {
      setLoading(true);
      const response = await fetch('/api/transcriptions');
      if (!response.ok) {
        throw new Error('Failed to fetch transcriptions');
      }
      const data = await response.json();
      setTranscriptions(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchTranscriptions();
  }, []);

  async function handleDelete() {
    if (deletingId === null) return;
    try {
      const response = await fetch(`/api/transcriptions/${deletingId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error('Failed to delete transcription');
      }
      // Refresh the list
      fetchTranscriptions();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="container mx-auto p-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Transcription History</CardTitle>
          <Link href="/transcribe">
            <Button variant="outline">Back to Transcribe</Button>
          </Link>
        </CardHeader>
        <CardContent>
          {loading && <p>Loading...</p>}
          {error && <p className="text-red-500">Error: {error}</p>}
          {!loading && !error && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Audio Source</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transcriptions.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>{t.id}</TableCell>
                    <TableCell className="max-w-xs truncate">{t.audio_source}</TableCell>
                    <TableCell>{new Date(t.created_at).toLocaleString()}</TableCell>
                    <TableCell className="flex items-center space-x-2">
                     <Link href={`/history/${t.id}`} className="text-blue-500 hover:underline">
                       View
                     </Link>
                     <Button variant="ghost" size="icon" onClick={() => setDeletingId(t.id)}>
                       <Trash2 className="h-4 w-4 text-red-500" />
                     </Button>
                   </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <AlertDialog open={!!deletingId} onOpenChange={(open) => !open && setDeletingId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the transcription.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-red-500 hover:bg-red-600">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}