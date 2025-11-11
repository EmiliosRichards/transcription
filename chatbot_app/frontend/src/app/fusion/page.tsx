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
      className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg p-6 flex flex-col items-center justify-center text-center min-h-40 w-full"
      onDrop={onDrop}
      onDragOver={onDragOver}
    >
      <Upload className="w-8 h-8 text-gray-400" />
      <p className="mt-2 text-gray-500 dark:text-gray-400 text-sm w-full truncate px-2">
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
  const COUNTDOWN_DEFAULT = 5;
  const [audio, setAudio] = useState<File | null>(null);
  const [teams, setTeams] = useState<File | null>(null);
  const [krisp, setKrisp] = useState<File | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string>("");
  const [artifacts, setArtifacts] = useState<{ name: string }[]>([]);
  const [teamsHints, setTeamsHints] = useState<string[]>([]);
  const [krispHints, setKrispHints] = useState<string[]>([]);
  const [refJson, setRefJson] = useState<File | null>(null);
  const [refHints, setRefHints] = useState<string[]>([]);
  const [startBlock, setStartBlock] = useState<string>("");
  const [endBlock, setEndBlock] = useState<string>("");
  const [runDir, setRunDir] = useState<string>("");
  const [skipExisting, setSkipExisting] = useState<boolean>(false);
  const [language, setLanguage] = useState<string>("de");
  const [vocabHints, setVocabHints] = useState<string>("Manuav, Altenhilfe, ambulant, stationär, teilstationär, ERP-System, Dienstplan, Dokumentation, Medifox, Vivendi, Telematik-Infrastruktur, Telematik, PeBeM, PBM, Personalbemessung, Tourenplanung, PDL, Awareness-Set, lead, Dexter, SENSO, Jabra, Plantronics");
  const [cleanupEnabled, setCleanupEnabled] = useState<boolean>(true);
  const [cleanupMaxTokens, setCleanupMaxTokens] = useState<string>("6000");
  const [cleanupConcurrency, setCleanupConcurrency] = useState<string>("4");
  const [includeContext, setIncludeContext] = useState<boolean>(true);
  const [diagnostics, setDiagnostics] = useState<boolean>(true);
  const [glossary, setGlossary] = useState<string>("Manuav, Altenhilfe, ambulant, stationär, teilstationär, ERP-System, Dienstplan, Dokumentation, Medifox, Vivendi, Telematik-Infrastruktur, Telematik, PeBeM, PBM, Personalbemessung, Tourenplanung, PDL, Awareness-Set, lead, Dexter, SENSO, Jabra, Plantronics");
  const [countdown, setCountdown] = useState<number>(0);
  const [countdownTotalMin, setCountdownTotalMin] = useState<number>(COUNTDOWN_DEFAULT);
  const [isFusionRun, setIsFusionRun] = useState<boolean>(false);
  const [smoothProgress, setSmoothProgress] = useState<number>(0);
  const timerStartRef = useRef<number | null>(null);
  const tickRef = useRef<number | null>(null);

  // Use same-origin relative API paths so Next.js rewrites can proxy to the backend (avoids CORS/egress)
  const apiBase = "";
  const pollRef = useRef<number | null>(null);
  const pollRefTranscribe = useRef<number | null>(null);

  const canRun = Boolean(teams && krisp && refJson);

  const startPolling = useCallback((id: string) => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const res = await fetch(`${apiBase}/api/tasks/${id}`);
        if (!res.ok) {
          throw new Error("Failed to fetch status");
        }
        const data: TaskStatus = await res.json();
        if (typeof data.progress === "number") setProgress(data.progress);
        if (data.message) setMessage(data.message);
        if (data.status === "SUCCESS") {
          window.clearInterval(pollRef.current!);
          if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
          setProgress(100);
          setSmoothProgress(100);
          setMessage("Fusion completed.");
          setError("");
          // Fetch artifacts list
          const ares = await fetch(`${apiBase}/api/fusion/${id}/artifacts`);
          if (ares.ok) {
            const ajson = await ares.json();
            setArtifacts(ajson.artifacts || []);
          }
          setIsLoading(false);
        } else if (data.status === "ERROR") {
          window.clearInterval(pollRef.current!);
          if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
          setIsLoading(false);
          setMessage("");
          setError(data.message || "Fusion failed.");
        }
      } catch (e) {
        window.clearInterval(pollRef.current!);
        if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
        setIsLoading(false);
        setMessage("Error while polling status");
      }
    }, 600);
  }, [backendUrl]);

  // Poller for transcribe-only flow
  const startPollingTranscribe = useCallback((id: string) => {
    setTaskId(id);
    if (pollRefTranscribe.current) window.clearInterval(pollRefTranscribe.current);
    pollRefTranscribe.current = window.setInterval(async () => {
      try {
        const res = await fetch(`${apiBase}/api/tasks/${id}`);
        if (!res.ok) throw new Error("Failed to fetch status");
        const data: TaskStatus = await res.json();
        if (data.status === 'SUCCESS') {
          window.clearInterval(pollRefTranscribe.current!);
          if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
          setSmoothProgress(100);
          const ares = await fetch(`${apiBase}/api/fusion/${id}/artifacts`);
          if (ares.ok) {
            const ajson = await ares.json();
            setArtifacts(ajson.artifacts || []);
          }
          setIsLoading(false);
          setMessage('Transcription completed.');
        } else if (data.status === 'ERROR') {
          window.clearInterval(pollRefTranscribe.current!);
          if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
          setIsLoading(false);
          setError(data.message || 'Transcription failed.');
        }
      } catch (_) {
        window.clearInterval(pollRefTranscribe.current!);
        if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
        setIsLoading(false);
        setError('Error while polling transcription.');
      }
    }, 700);
  }, [backendUrl]);

  // Start transcribe-only
  const onRunTranscribe = useCallback(async () => {
    if (!audio || !teams) return;
    setIsLoading(true);
    setArtifacts([]);
    setError("");
    setMessage("Uploading and transcribing...");
    // initialize smooth time-based progress similar to fusion
    if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
    setProgress(10);
    setIsFusionRun(false);
    setCountdownTotalMin(5);
    setCountdown(5);
    timerStartRef.current = Date.now();
    setSmoothProgress(10);
    try {
      const form = new FormData();
      form.append('audio', audio);
      form.append('teams', teams);
      if (language) form.append('language', language);
      if (vocabHints) form.append('vocab_hints', vocabHints);
      const res = await fetch(`${apiBase}/api/fusion/transcribe-only`, { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to start transcription');
      }
      const data = await res.json();
      if (data.task_id) startPollingTranscribe(data.task_id);
    } catch (e: any) {
      setIsLoading(false);
      setError(e.message || 'Failed to start transcription');
    }
  }, [audio, teams, language, vocabHints, startPollingTranscribe]);

  // Lightweight client-side file content checks to guide users before submit
  const validateTeams = useCallback(async (file: File) => {
    const hints: string[] = [];
    try {
      const text = await file.text();
      const header = text.slice(0, 64).toUpperCase();
      const hasWebvtt = header.includes('WEBVTT');
      const looksSrt = /\d{1,2}:\d{2}:\d{2},\d{3}\s+-->/.test(text);
      const hasVttTimes = /(\d{1,2}:)?\d{2}:\d{2}\.\d{3}\s+-->/.test(text);
      const hasSpeaker = /<v\s+[^>]+>.*<\/v>|^[^:]{1,60}:\s+/m.test(text);
      if (!hasWebvtt) hints.push('Teams: Missing WEBVTT header at top of file.');
      if (looksSrt) hints.push('Teams: Timestamps look like SRT (comma). Convert to VTT (use periods).');
      if (!hasVttTimes) hints.push('Teams: No valid VTT cue times found (MM:SS.mmm or HH:MM:SS.mmm).');
      if (!hasSpeaker) hints.push('Teams: No speaker tags (<v Name>…</v>) or "Name: text" lines detected.');
    } catch (_) {
      hints.push('Teams: Could not read file content.');
    }
    setTeamsHints(hints);
  }, []);
  const validateKrisp = useCallback(async (file: File) => {
    const hints: string[] = [];
    try {
      const text = await file.text();
      const headerOk = /^.+\|\s*\d{1,2}:\d{2}\s*$/m.test(text);
      const lineOk = /^\s*\[\d{1,2}:\d{2}\]\s*.+?:/m.test(text);
      if (!headerOk && !lineOk) {
        hints.push('Krisp: No headers found. Use "Speaker | mm:ss" or "[mm:ss] Speaker: text".');
      }
    } catch (_) {
      hints.push('Krisp: Could not read file content.');
    }
    setKrispHints(hints);
  }, []);

  const validateRefJson = useCallback(async (file: File) => {
    const hints: string[] = [];
    if (!file.name.toLowerCase().endsWith('.json')) {
      hints.push('Reference must be a .json produced by the transcriber.');
    }
    try {
      const text = await file.text();
      const obj = JSON.parse(text);
      let seq: any[] = [];
      if (Array.isArray(obj)) {
        seq = obj;
      } else if (obj && Array.isArray(obj.segments)) {
        seq = obj.segments;
      } else {
        hints.push('Invalid schema: expected an array or an object with a "segments" array.');
      }

      if (seq.length === 0) {
        hints.push('No segments found in reference JSON.');
      } else {
        // Basic field checks on a small sample
        const sample = seq.slice(0, Math.min(10, seq.length));
        const missingTs = sample.filter((s: any) => (
          s == null || (s.t_start == null && s.t == null && s.start == null)
        )).length;
        if (missingTs > 0) {
          hints.push('Some segments missing timestamp fields (start/t_start/t).');
        }
        const missingText = sample.filter((s: any) => !s || typeof s.text !== 'string' || s.text.trim().length === 0).length;
        if (missingText > 0) {
          hints.push('Some segments missing non-empty text strings.');
        }
        if (hints.length === 0) {
          hints.push(`Looks good: ${seq.length} segments detected.`);
        }
      }
    } catch (e) {
      hints.push('Could not parse JSON file.');
    }
    setRefHints(hints);
  }, []);

  const onRun = useCallback(async () => {
    if (!teams || !krisp) return;
    if (!refJson) { setError('Reference (GPT) .json is required'); return; }
    // Client-side validation for clearer UX
    const tOk = teams.name.toLowerCase().endsWith('.vtt');
    const kOk = krisp.name.toLowerCase().endsWith('.txt');
    if (!tOk || !kOk) {
      const errs = [] as string[];
      if (!tOk) errs.push('Teams must be a .vtt');
      if (!kOk) errs.push('Krisp must be a .txt');
      setError(errs.join(' • '));
      return;
    }
    setIsLoading(true);
    setArtifacts([]);
    setProgress(10);
    setMessage("Uploading files...");
    setError("");
    // initialize countdown and smooth timer
    if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
    setIsFusionRun(true);
    setCountdownTotalMin(10);
    setCountdown(10);
    timerStartRef.current = Date.now();
    setSmoothProgress(10);
    try {
      const form = new FormData();
      form.append("teams", teams);
      form.append("krisp", krisp);
      form.append("ref", refJson);
      if (startBlock) form.append("start_block", startBlock);
      if (endBlock) form.append("end_block", endBlock);
      if (runDir) form.append("run_dir", runDir);
      if (skipExisting) form.append("skip_existing", "true");
      if (cleanupEnabled) {
        form.append("cleanup_enabled", "true");
        form.append("cleanup_max_tokens", cleanupMaxTokens || "6000");
        form.append("cleanup_model", "gpt-5-2025-08-07");
        form.append("cleanup_concurrency", cleanupConcurrency || "4");
      }
      if (includeContext) form.append("include_context", "true");
      if (diagnostics) form.append("diagnostics", "true");
      if (glossary) form.append("glossary", glossary);
      // Auto-offset defaults
      form.append("auto_offset_enabled", "true");
      form.append("offset_adjust_gpt", "true");
      form.append("offset_min_phrase_tokens", "4");
      form.append("offset_max_phrase_tokens", "10");
      form.append("offset_expand_tokens", "2");
      form.append("offset_similarity_threshold", "0.66");
      form.append("offset_trim_pad_sec", "2");
      const res = await fetch(`${apiBase}/api/fusion/run`, { method: "POST", body: form });
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
  }, [teams, krisp, refJson, startBlock, endBlock, runDir, skipExisting, cleanupEnabled, cleanupMaxTokens, cleanupConcurrency, includeContext, diagnostics, glossary, startPolling]);

  const onExtractOnly = useCallback(async () => {
    if (!runDir) return;
    setIsLoading(true);
    setArtifacts([]);
    setProgress(10);
    setMessage("Running extract-products...");
    setError("");
    if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
    setIsFusionRun(false);
    setCountdownTotalMin(5);
    setCountdown(5);
    timerStartRef.current = Date.now();
    setSmoothProgress(10);
    try {
      const form = new FormData();
      form.append("run_dir", runDir);
      const res = await fetch(`${apiBase}/api/fusion/extract`, { method: "POST", body: form });
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
  }, [runDir, startPolling]);

  // Smooth progress + derived minute countdown synced to a 5-minute timer
  useEffect(() => {
    if (isLoading && timerStartRef.current !== null) {
      if (tickRef.current) { window.clearInterval(tickRef.current); }
      tickRef.current = window.setInterval(() => {
        const start = timerStartRef.current as number;
        const total = countdownTotalMin * 60000;
        const elapsed = Date.now() - start;
        const frac = Math.min(Math.max(elapsed / total, 0), 1);
        // Update progress 10% → 90% linearly
        setSmoothProgress(10 + Math.round(frac * 80));
        // Update minute display
        const remainingMs = Math.max(0, total - elapsed);
        const remainingMin = Math.max(1, Math.ceil(remainingMs / 60000));
        setCountdown(remainingMin);
        if (elapsed > total && isFusionRun) {
          setMessage("Fusion is taking a little longer than expected. Please wait.");
        }
      }, 200);
    } else {
      if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
    }
    return () => {
      if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
    };
  }, [isLoading]);

  // Display whichever is higher: backend-reported progress or smooth timer
  const displayProgress = Math.max(progress, smoothProgress);

  return (
    <div className="p-6 min-h-screen flex flex-col items-center">
      <div className="w-full max-w-4xl">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-semibold">Transcript Fusion</h1>
          <p className="text-muted-foreground text-sm mt-1">1) Generate GPT transcript from Audio. 2) Fuse GPT + Krisp + Teams.</p>
        </div>
        {/* Section 1: Transcribe-only */}
        <Card className="w-full">
          <CardHeader>
            <CardTitle>1) Generate GPT Transcript from Audio</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <DropBox label="Audio (.mp3/.mp4/.wav/.m4a)" accept=".mp3,.mp4,.wav,.m4a" file={audio} onFileSelected={setAudio} />
              <DropBox label="Teams (.vtt)" accept=".vtt" file={teams} onFileSelected={(f) => { setTeams(f); setTeamsHints([]); if (f) validateTeams(f); }} />
              <div className="grid grid-cols-1 gap-3">
                <Input placeholder="language (e.g., de, en)" value={language} onChange={(e) => setLanguage(e.target.value)} />
                <Input placeholder="Vocab hints (comma-separated)" value={vocabHints} onChange={(e) => setVocabHints(e.target.value)} />
              </div>
            </div>
            <div className="flex justify-center">
              <Button onClick={onRunTranscribe} disabled={!(audio && teams)} variant="ghost" className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm">Transcribe Audio</Button>
            </div>
          </CardContent>
        </Card>

        {/* Section 2: Fusion */}
        <Card className="w-full mt-6">
          <CardHeader>
            <CardTitle>2) Fuse GPT Transcript + Krisp + Teams</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <DropBox label="Reference (GPT) .json" accept=".json" file={refJson || null} onFileSelected={(f) => { setRefJson(f || null); setRefHints([]); if (f) validateRefJson(f); }} />
              <DropBox label="Teams (.vtt)" accept=".vtt" file={teams} onFileSelected={(f) => { setTeams(f); setTeamsHints([]); if (f) validateTeams(f); }} />
              <DropBox label="Krisp (.txt)" accept=".txt" file={krisp} onFileSelected={(f) => { setKrisp(f); setKrispHints([]); if (f) validateKrisp(f); }} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Input placeholder="Glossary (comma-separated)" value={glossary} onChange={(e) => setGlossary(e.target.value)} />
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input type="checkbox" checked={includeContext} onChange={(e) => setIncludeContext(e.target.checked)} />
                Include context
              </label>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input type="checkbox" checked={diagnostics} onChange={(e) => setDiagnostics(e.target.checked)} />
                Diagnostics
              </label>
            </div>
            {(teamsHints.length || krispHints.length || refHints.length) ? (
              <Card className="w-full border-amber-300/40">
                <CardHeader>
                  <CardTitle className="text-amber-500 text-sm">Suggestions</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="text-sm text-amber-600 dark:text-amber-400 space-y-1 list-disc ml-5">
                    {teamsHints.map((h, i) => (<li key={`t-${i}`}>{h}</li>))}
                    {krispHints.map((h, i) => (<li key={`k-${i}`}>{h}</li>))}
                    {refHints.map((h, i) => (<li key={`r-${i}`}>{h}</li>))}
                  </ul>
                </CardContent>
              </Card>
            ) : null}
            {isLoading ? (
              <div className="flex flex-col items-center gap-2">
                <Progress value={displayProgress} className="w-full [&>div]:bg-blue-500" />
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
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input type="checkbox" checked={cleanupEnabled} onChange={(e) => setCleanupEnabled(e.target.checked)} />
                AI wording cleanup
              </label>
              {cleanupEnabled && (
                <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Input placeholder="Max tokens per batch (e.g., 6000)" value={cleanupMaxTokens} onChange={(e) => setCleanupMaxTokens(e.target.value)} />
                  <Input placeholder="Cleanup concurrency (e.g., 4)" value={cleanupConcurrency} onChange={(e) => setCleanupConcurrency(e.target.value)} />
                </div>
              )}
                <Button onClick={onExtractOnly} disabled={!runDir} variant="ghost" className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm">
                  Extract Products Only
                </Button>
                {error && (
                  <div className="flex flex-col items-center gap-2 w-full">
                    <p className="text-sm text-red-400 text-center">{error}</p>
                    <div className="flex gap-2">
                      <Button onClick={() => { setError(""); onRun(); }} size="sm" variant="outline">Retry</Button>
                      <Button onClick={() => setError("")} size="sm" variant="ghost">Dismiss</Button>
                    </div>
                  </div>
                )}
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
                      href={`/api/fusion/${taskId}/download?name=${encodeURIComponent(a.name)}`}
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


