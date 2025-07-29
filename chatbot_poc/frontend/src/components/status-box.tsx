"use client";

import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

const messages = [
  "Understanding your request...",
  "Finding relevant transcripts...",
  "Analyzing the data...",
  "Compiling the answer...",
];

export function StatusBox() {
  const [currentMessageIndex, setCurrentMessageIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentMessageIndex((prevIndex) => (prevIndex + 1) % messages.length);
    }, 2000); // Change message every 2 seconds

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center justify-center p-4 rounded-lg bg-muted">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      <p className="text-sm text-muted-foreground">{messages[currentMessageIndex]}</p>
    </div>
  );
}