"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

interface TranscriptDialogProps {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  transcript: {
    customer_id: string;
    full_journey: string;
    call_ids: string;
  } | null;
}

export function TranscriptDialog({ isOpen, onOpenChange, transcript }: TranscriptDialogProps) {
  if (!transcript) {
    return null;
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Full Transcript for Customer: {transcript.customer_id}</DialogTitle>
          <DialogDescription>
            Call IDs: {transcript.call_ids}
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="h-[60vh] mt-4">
          <pre className="whitespace-pre-wrap text-sm">
            {transcript.full_journey}
          </pre>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}