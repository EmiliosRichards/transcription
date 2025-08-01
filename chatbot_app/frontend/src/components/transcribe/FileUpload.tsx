"use client";

import { Upload } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface FileUploadProps {
  file: File | null;
  onFileChange: (file: File | null) => void;
}

export function FileUpload({ file, onFileChange }: FileUploadProps) {
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      onFileChange(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files) {
      onFileChange(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  return (
    <div
      className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg p-8 flex flex-col items-center justify-center text-center"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <Upload className="w-12 h-12 text-gray-400" />
      <p className="mt-4 text-gray-500 dark:text-gray-400">
        {file ? file.name : "Drag & drop a file here, or click to select a file"}
      </p>
      <Input
        type="file"
        className="hidden"
        id="file-upload"
        onChange={handleFileChange}
        accept="audio/*"
      />
      <Button asChild variant="outline" className="mt-4">
        <label htmlFor="file-upload">Select File</label>
      </Button>
    </div>
  );
}