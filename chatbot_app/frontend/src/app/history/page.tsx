"use client";

import { useEffect } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { useTranscriptionStore } from '@/lib/stores/useTranscriptionStore';

export default function HistoryPage() {
  const { transcriptions, setTranscriptions } = useTranscriptionStore();

  useEffect(() => {
    async function fetchTranscriptions() {
      try {
        const response = await fetch('/api/transcriptions');
        if (!response.ok) {
          throw new Error('Failed to fetch transcriptions');
        }
        const data = await response.json();
        setTranscriptions(data);
      } catch (error) {
        console.error(error);
      }
    }
    fetchTranscriptions();
  }, [setTranscriptions]);

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
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Transcription ID</TableHead>
                <TableHead>Audio Source</TableHead>
                <TableHead>Created At</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {transcriptions.map((transcription) => (
                <TableRow key={transcription.id}>
                  <TableCell>{transcription.id}</TableCell>
                  <TableCell className="max-w-xs truncate">{transcription.audio_source || 'N/A'}</TableCell>
                  <TableCell>{new Date(transcription.created_at).toLocaleString()}</TableCell>
                  <TableCell>
                    <Link href={`/history/${transcription.id}`}>
                      <Button variant="link">View Details</Button>
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}