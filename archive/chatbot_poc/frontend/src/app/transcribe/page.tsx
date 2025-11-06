"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload, Link as LinkIcon, Loader2 } from "lucide-react";
import Link from "next/link";
import ConversationView from "@/components/ConversationView";

export default function TranscribePage() {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [transcription, setTranscription] = useState("");
  const [transcriptionId, setTranscriptionId] = useState<number | null>(null);
  const [processedTranscription, setProcessedTranscription] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isCorrecting, setIsCorrecting] = useState(false);
  const [correctCompanyName, setCorrectCompanyName] = useState("");
  const [error, setError] = useState("");
  const resultCardRef = useRef<HTMLDivElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFile(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleSubmit = async () => {
    setIsLoading(true);
    setTranscription("");
    setTranscriptionId(null);
    setProcessedTranscription("");

    const formData = new FormData();
    if (file) {
      formData.append("file", file);
    } else if (url) {
      formData.append("url", url);
    }

    try {
      const response = await fetch("/api/transcribe", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to transcribe audio");
      }

      const result = await response.json();
      setTranscription(result.transcription);
      setTranscriptionId(result.transcription_id);
    } catch (error) {
      console.error(error);
      setError("An error occurred during transcription.");
    } finally {
      setIsLoading(false);
    }
  };

  const handlePostProcess = async () => {
    if (!transcription) return;
    setIsProcessing(true);
    setError("");
    try {
      const response = await fetch("/api/post-process-transcription", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ transcription, transcription_id: transcriptionId }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to process transcription.");
      }

      const data = await response.json();
      setProcessedTranscription(data.processed_transcription);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  useEffect(() => {
    if ((transcription || error) && resultCardRef.current) {
      resultCardRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [transcription, error]);


  const handleCorrectCompanyName = async () => {
    if (!processedTranscription || !correctCompanyName) return;
    setIsCorrecting(true);
    setError("");
    try {
      const response = await fetch("/api/correct-company-name", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          full_transcript: processedTranscription,
          correct_company_name: correctCompanyName,
          transcription_id: transcriptionId,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to correct company name.");
      }

      const data = await response.json();
      // Update the processed transcription with the corrected one
      setProcessedTranscription(data.corrected_transcript);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsCorrecting(false);
    }
  };

  return (
    <div className="p-6 min-h-screen flex flex-col items-center">
      <div className="w-full max-w-4xl">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl text-gray-800 dark:text-white">Transcribe Audio</h1>
          <div className="flex gap-2">
            <Link href="/history">
                <Button variant="outline">View History</Button>
            </Link>
            <Link href="/">
                <Button>Back to Chatbot</Button>
            </Link>
          </div>
        </div>
        <Card className="w-full">
          <CardHeader>
            <CardTitle>Upload Audio File or Provide URL</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
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
            <div className="flex flex-col justify-center">
              <div className="flex items-center gap-2 mb-4">
                <LinkIcon className="w-6 h-6 text-gray-400" />
                <p className="text-gray-500 dark:text-gray-400">Or provide a URL</p>
              </div>
              <Input
                type="url"
                placeholder="https://example.com/audio.mp3"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
            <div className="mt-6 flex justify-center">
              <Button onClick={handleSubmit} disabled={isLoading || (!file && !url)}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {isLoading ? "Transcribing..." : "Transcribe"}
              </Button>
            </div>
          </CardContent>
        </Card>
        <div className="w-full max-w-4xl mt-4 text-center">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Please note: This transcription is generated by an AI and may contain inaccuracies. Names and technical terms can sometimes be misinterpreted.
            </p>
        </div>
        {(transcription || processedTranscription) && (
          <div ref={resultCardRef} className="w-full max-w-4xl">
            <Card className="mt-6">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Transcription Result</CardTitle>
                {transcription && !processedTranscription && (
                  <Button
                    onClick={handlePostProcess}
                    disabled={isProcessing}
                    className="bg-gradient-to-r from-blue-700 to-blue-500 text-white"
                  >
                    {isProcessing ? "Processing..." : "Process Transcription"}
                  </Button>
                )}
              </CardHeader>
              <CardContent>
                {processedTranscription ? (
                  <ConversationView transcription={processedTranscription} />
                ) : (
                  <p className="whitespace-pre-wrap">{transcription}</p>
                )}
              </CardContent>
            </Card>
            {/* {processedTranscription && (
              <Card className="mt-4">
                <CardHeader>
                  <CardTitle>Correct Company Name</CardTitle>
                </CardHeader>
                <CardContent className="flex items-center gap-4">
                  <Input
                    placeholder="Enter correct company name..."
                    value={correctCompanyName}
                    onChange={(e) => setCorrectCompanyName(e.target.value)}
                    className="flex-grow"
                  />
                  <Button onClick={handleCorrectCompanyName} disabled={isCorrecting || !correctCompanyName}>
                    {isCorrecting ? "Correcting..." : "Correct Name"}
                  </Button>
                </CardContent>
              </Card>
            )} */}
          </div>
        )}
        <div className="h-96" />
      </div>
    </div>
  );
}