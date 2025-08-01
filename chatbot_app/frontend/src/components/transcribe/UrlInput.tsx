"use client";

import { Input } from "@/components/ui/input";
import { Link as LinkIcon } from "lucide-react";

interface UrlInputProps {
  url: string;
  onUrlChange: (url: string) => void;
}

export function UrlInput({ url, onUrlChange }: UrlInputProps) {
  return (
    <div className="flex flex-col justify-center">
      <div className="flex items-center gap-2 mb-4">
        <LinkIcon className="w-6 h-6 text-gray-400" />
        <p className="text-gray-500 dark:text-gray-400">Or provide a URL</p>
      </div>
      <Input
        type="url"
        placeholder="https://example.com/audio.mp3"
        value={url}
        onChange={(e) => onUrlChange(e.target.value)}
      />
    </div>
  );
}