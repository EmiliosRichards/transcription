"use client";

import { useCallback, useState } from 'react';
import { Upload } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useMediaReviewStore } from "@/lib/stores/useMediaReviewStore";
import { parseWebVttToCues } from "@/lib/utils/vtt";

type LoadedFiles = {
  video?: string;
  audio?: string;
  vtt?: string;
  docx?: string;
};

export default function MediaUpload() {
  const {
    setVideoUrl,
    setAudioUrl,
    setVttCues,
    setDocxText,
  } = useMediaReviewStore();

  const [loaded, setLoaded] = useState<LoadedFiles>({});

  const handleFiles = useCallback(async (fileList: FileList) => {
    const nextLoaded: LoadedFiles = { ...loaded };
    for (const file of Array.from(fileList)) {
      const lowerName = file.name.toLowerCase();
      const type = file.type;

      if (type.startsWith('video/')) {
        const url = URL.createObjectURL(file);
        setVideoUrl(url);
        nextLoaded.video = file.name;
      } else if (type.startsWith('audio/')) {
        const url = URL.createObjectURL(file);
        setAudioUrl(url);
        nextLoaded.audio = file.name;
      } else if (lowerName.endsWith('.vtt') || type === 'text/vtt') {
        const text = await file.text();
        const cues = parseWebVttToCues(text);
        setVttCues(cues);
        nextLoaded.vtt = file.name;
      } else if (lowerName.endsWith('.docx') || type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
        // Placeholder parse: show a simple message; full parse can use mammoth later
        const buf = await file.arrayBuffer();
        setDocxText(`Loaded DOCX “${file.name}” (${buf.byteLength} bytes).`);
        nextLoaded.docx = file.name;
      }
    }
    setLoaded(nextLoaded);
  }, [loaded, setVideoUrl, setAudioUrl, setVttCues, setDocxText]);

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      handleFiles(e.target.files);
    }
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  return (
    <div>
      <div
        className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg p-8 flex flex-col items-center justify-center text-center"
        onDrop={onDrop}
        onDragOver={onDragOver}
      >
        <Upload className="w-12 h-12 text-gray-400" />
        <p className="mt-4 text-gray-500 dark:text-gray-400">
          Drag & drop .vtt plus a video or audio file here, or click to select
        </p>
        <Input
          type="file"
          className="hidden"
          id="media-upload"
          onChange={onInputChange}
          multiple
          accept=".vtt,video/*,audio/*"
        />
        <Button asChild variant="ghost" className="mt-4 rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm">
          <label htmlFor="media-upload">Select Files</label>
        </Button>
      </div>

      {(loaded.video || loaded.audio || loaded.vtt || loaded.docx) && (
        <div className="mt-4 text-sm text-gray-600 dark:text-gray-300">
          <div className="font-medium mb-1">Loaded:</div>
          <ul className="list-disc ml-5 space-y-1">
            {loaded.video && <li>Video: {loaded.video}</li>}
            {loaded.audio && <li>Audio: {loaded.audio}</li>}
            {loaded.vtt && <li>VTT: {loaded.vtt}</li>}
            {loaded.docx && <li>DOCX: {loaded.docx}</li>}
          </ul>
        </div>
      )}
    </div>
  );
}


