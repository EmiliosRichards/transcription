"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Upload } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

type TaskStatus = {
  status: string;
  progress?: number;
  message?: string;
  result?: {
    run_dir?: string;
    artifacts?: { name: string }[];
  };
};

function DropBox({
  label,
  accept,
  file,
  onFileSelected,
}: {
  label: string;
  accept: string;
  file: File | null;
  onFileSelected: (f: File | null) => void;
}) {
  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileSelected(e.target.files[0]);
    }
  };
  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileSelected(e.dataTransfer.files[0]);
    }
  };
  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };
  return (
    <div
      className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg p-6 flex flex-col items-center justify-center text-center min-h-40"
      onDrop={onDrop}
      onDragOver={onDragOver}
    >
      <Upload className="w-8 h-8 text-gray-400" />
      <p className="mt-2 text-gray-500 dark:text-gray-400 text-sm">
        {file ? file.name : label}
      </p>
      <Input type="file" className="hidden" id={label} onChange={onInputChange} accept={accept} />
      <Button asChild variant="ghost" className="mt-3 rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm">
        <label htmlFor={label}>Select File</label>
      </Button>
    </div>
  );
}

export default function FusionPage() {
  const [teams, setTeams] = useState<File | null>(null);
  const [charla, setCharla] = useState<File | null>(null);
  const [krisp, setKrisp] = useState<File | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string>("");
  const [artifacts, setArtifacts] = useState<{ name: string }[]>([]);
  const [startBlock, setStartBlock] = useState<string>("");
  const [endBlock, setEndBlock] = useState<string>("");
  const [runDir, setRunDir] = useState<string>("");
  const [skipExisting, setSkipExisting] = useState<boolean>(false);
  const [countdown, setCountdown] = useState<number>(0);
  const countdownRef = useRef<number | null>(null);

  const backendUrl = useMemo(() => process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000", []);
  const pollRef = useRef<number | null>(null);

  const canRun = teams && charla && krisp;

  const startPolling = useCallback((id: string) => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const res = await fetch(`${backendUrl}/api/tasks/${id}`);
        if (!res.ok) {
          throw new Error("Failed to fetch status");
        }
        const data: TaskStatus = await res.json();
        if (typeof data.progress === "number") setProgress(data.progress);
        if (data.message) setMessage(data.message);
        if (data.status === "SUCCESS") {
          window.clearInterval(pollRef.current!);
          if (countdownRef.current) { window.clearInterval(countdownRef.current); countdownRef.current = null; }
          setProgress(100);
          setMessage("Fusion completed.");
          // Fetch artifacts list
          const ares = await fetch(`${backendUrl}/api/fusion/${id}/artifacts`);
          if (ares.ok) {
            const ajson = await ares.json();
            setArtifacts(ajson.artifacts || []);
          }
          setIsLoading(false);
        } else if (data.status === "ERROR") {
          window.clearInterval(pollRef.current!);
          if (countdownRef.current) { window.clearInterval(countdownRef.current); countdownRef.current = null; }
          setIsLoading(false);
          setMessage(data.message || "Error");
        }
      } catch (e) {
        window.clearInterval(pollRef.current!);
        if (countdownRef.current) { window.clearInterval(countdownRef.current); countdownRef.current = null; }
        setIsLoading(false);
        setMessage("Error while polling status");
      }
    }, 600);
  }, [backendUrl]);

  const onRun = useCallback(async () => {
    if (!teams || !charla || !krisp) return;
    setIsLoading(true);
    setArtifacts([]);
    setProgress(5);
    setMessage("Uploading files...");
    setError("");
    // initialize countdown
    if (countdownRef.current) { window.clearInterval(countdownRef.current); countdownRef.current = null; }
    setCountdown(5);
    try {
      const form = new FormData();
      form.append("teams", teams);
      form.append("charla", charla);
      form.append("krisp", krisp);
      if (startBlock) form.append("start_block", startBlock);
      if (endBlock) form.append("end_block", endBlock);
      if (runDir) form.append("run_dir", runDir);
      if (skipExisting) form.append("skip_existing", "true");
      const res = await fetch(`${backendUrl}/api/fusion/run`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to start fusion");
      }
      const data = await res.json();
      if (data.task_id) {
        setTaskId(data.task_id);
        startPolling(data.task_id);
      } else {
        throw new Error("No task id returned");
      }
    } catch (e: any) {
      setIsLoading(false);
      setError(e.message || "Failed to start fusion");
    }
  }, [backendUrl, teams, charla, krisp, startBlock, endBlock, runDir, skipExisting, startPolling]);

  const onExtractOnly = useCallback(async () => {
    if (!runDir) return;
    setIsLoading(true);
    setArtifacts([]);
    setProgress(10);
    setMessage("Running extract-products...");
    setError("");
    if (countdownRef.current) { window.clearInterval(countdownRef.current); countdownRef.current = null; }
    setCountdown(5);
    try {
      const form = new FormData();
      form.append("run_dir", runDir);
      const res = await fetch(`${backendUrl}/api/fusion/extract`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to start extract");
      }
      const data = await res.json();
      if (data.task_id) {
        setTaskId(data.task_id);
        startPolling(data.task_id);
      }
    } catch (e: any) {
      setIsLoading(false);
      setError(e.message || "Failed to start extract");
    }
  }, [backendUrl, runDir, startPolling]);

  // Start/stop minute-based countdown while loading
  useEffect(() => {
    if (isLoading) {
      if (countdownRef.current) { window.clearInterval(countdownRef.current); }
      countdownRef.current = window.setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (countdownRef.current) { window.clearInterval(countdownRef.current); countdownRef.current = null; }
            return 1;
          }
          return prev - 1;
        });
      }, 60000);
    } else {
      if (countdownRef.current) { window.clearInterval(countdownRef.current); countdownRef.current = null; }
    }
    return () => {
      if (countdownRef.current) { window.clearInterval(countdownRef.current); countdownRef.current = null; }
    };
  }, [isLoading]);

  return (
    <div className="p-6 min-h-screen flex flex-col items-center">
      <div className="w-full max-w-4xl">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-semibold">Transcript Fusion</h1>
          <p className="text-muted-foreground text-sm mt-1">Drop your Teams (.vtt), Charla (.txt), and Krisp (.txt)</p>
        </div>
        <Card className="w-full">
          <CardHeader>
            <CardTitle>Upload Files</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <DropBox label="Teams (.vtt)" accept=".vtt" file={teams} onFileSelected={setTeams} />
              <DropBox label="Charla (.txt)" accept=".txt" file={charla} onFileSelected={setCharla} />
              <DropBox label="Krisp (.txt)" accept=".txt" file={krisp} onFileSelected={setKrisp} />
            </div>
            {isLoading ? (
              <div className="flex flex-col items-center gap-2">
                <Progress value={progress} className="w-full [&>div]:bg-blue-500" />
                <p className="text-sm text-muted-foreground">{message}</p>
                <div className="relative h-6 w-full overflow-hidden">
                  <AnimatePresence mode="popLayout" initial={false}>
                    {countdown >= 1 && (
                      <motion.p
                        key={countdown}
                        initial={{ y: 12, opacity: 0, scale: 0.95 }}
                        animate={{ y: 0, opacity: 1, scale: 1 }}
                        exit={{ y: -12, opacity: 0, scale: 0.98 }}
                        transition={{ duration: 0.4 }}
                        className="text-xs text-muted-foreground text-center"
                      >
                        {countdown} minute{countdown !== 1 ? "s" : ""} remaining
                      </motion.p>
                    )}
                  </AnimatePresence>
                </div>
              </div>
            ) : (
              <div className="mt-2 flex flex-col items-center gap-3">
                <Button onClick={onRun} disabled={!canRun} variant="ghost" className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm">
                  Run Fusion
                </Button>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 w-full">
                  <Input placeholder="start-block (optional)" value={startBlock} onChange={(e) => setStartBlock(e.target.value)} />
                  <Input placeholder="end-block (optional)" value={endBlock} onChange={(e) => setEndBlock(e.target.value)} />
                  <Input placeholder="run-dir (optional, e.g., run_YYYYMMDD_HHMMSS)" value={runDir} onChange={(e) => setRunDir(e.target.value)} />
                </div>
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" checked={skipExisting} onChange={(e) => setSkipExisting(e.target.checked)} />
                  Skip existing blocks
                </label>
                <Button onClick={onExtractOnly} disabled={!runDir} variant="ghost" className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm">
                  Extract Products Only
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {artifacts.length > 0 && (
          <Card className="w-full mt-4">
            <CardHeader>
              <CardTitle>Downloads</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="list-disc ml-5 space-y-2">
                {artifacts.map((a) => (
                  <li key={a.name}>
                    <a
                      className="text-blue-600 hover:underline"
                      href={`${backendUrl}/api/fusion/${taskId}/download?name=${encodeURIComponent(a.name)}`}
                    >
                      {a.name}
                    </a>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
        {error && (
          <Card className="w-full mt-4 border-red-300/40">
            <CardHeader>
              <CardTitle className="text-red-400">Error</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-red-300 whitespace-pre-wrap">{error}</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}


