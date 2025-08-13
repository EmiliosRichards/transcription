"use client";

import MediaUpload from "@/components/media/MediaUpload";
import VideoPlayer from "@/components/media/VideoPlayer";
import TranscriptViewer from "@/components/media/TranscriptViewer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
 

export default function MediaPage() {
  const router = useRouter();
  const [focusMode, setFocusMode] = useState(false);
  useEffect(() => {
    const original = document.body.style.overflow;
    if (focusMode) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = original || '';
    }
    return () => {
      document.body.style.overflow = original || '';
    };
  }, [focusMode]);
  return (
    <div className="relative min-h-screen w-full overflow-hidden">
      <div className="mx-auto w-full px-6 pt-4 pb-4" style={{ maxWidth: focusMode ? '100%' : '72rem' }}>
        {!focusMode && (
          <div className="mb-6">
            <div className="flex items-center justify-between">
              <h1 className="text-3xl text-gray-800 dark:text-white">Media Review</h1>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"
                  size="sm"
                  onClick={() => router.back()}
                >
                  Back
                </Button>
                <Button
                  variant="ghost"
                  className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"
                  size="sm"
                  onClick={() => setFocusMode(true)}
                >
                  Focus Mode
                </Button>
              </div>
            </div>
          </div>
        )}

        {!focusMode && (
          <div className="mb-6">
            <Card>
              <CardContent>
                <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">
                  Drag and drop a video/audio file plus a VTT transcript.
                </p>
                <MediaUpload />
              </CardContent>
            </Card>
          </div>
        )}

        {!focusMode ? (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(320px,0.35fr)_1fr] gap-6">
            <div>
              <Card>
                <CardHeader>
                  <CardTitle>Player</CardTitle>
                </CardHeader>
                <CardContent>
                  <VideoPlayer compact />
                </CardContent>
              </Card>
            </div>
            <div>
              <Card>
                <CardHeader>
                  <CardTitle>Transcript</CardTitle>
                </CardHeader>
                <CardContent>
                  <TranscriptViewer />
                </CardContent>
              </Card>
            </div>
          </div>
        ) : (
          <div className="fixed inset-x-4 top-4 bottom-4 overflow-x-hidden">
            <div className="absolute inset-0 -z-10 rounded-xl backdrop-blur-md bg-gray-900/20 border border-white/10 shadow-[0_10px_30px_-10px_rgba(0,0,0,0.5)]" />
            <div className="grid h-full grid-cols-1 xl:grid-cols-[minmax(640px,0.55fr)_1fr] gap-6 p-6 rounded-xl overflow-hidden">
              <div className="flex flex-col min-h-0">
                <VideoPlayer dense />
              </div>
              <div className="min-h-0 p-2">
                <TranscriptViewer
                  heightClass="h-full"
                  extraActions={
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"
                      onClick={() => setFocusMode(false)}
                    >
                      Exit Focus
                    </Button>
                  }
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


