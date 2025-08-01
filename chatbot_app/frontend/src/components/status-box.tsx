"use client";

import { Loader2 } from 'lucide-react';

interface StatusBoxProps {
  status: string;
}

export function StatusBox({ status }: StatusBoxProps) {
  return (
    <div className="flex items-center justify-center p-4 rounded-lg bg-muted animate-pulse">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      <p className="text-sm text-muted-foreground">{status}</p>
    </div>
  );
}