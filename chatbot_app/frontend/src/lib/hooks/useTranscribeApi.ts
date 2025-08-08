import { useTranscribeStore, TranscriptionItem } from '../stores/useTranscribeStore';
import { useCallback } from 'react';

export function useTranscribeApi() {
  const {
    file,
    url,
    transcription,
    transcriptionId,
    processedTranscription,
    correctCompanyName,
    setIsLoading,
    setTranscription,
    setTranscriptionId,
    setProcessedTranscription,
    setAudioUrl,
    setIsProcessing,
    setIsCorrecting,
    setError,
    setProgress,
    setProcessingProgress,
    setHistory,
  } = useTranscribeStore();

  const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

  const pollTaskStatus = async (taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${backendUrl}/api/tasks/${taskId}`);
        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: response.statusText }));
          throw new Error(`Failed to get task status: ${err.detail}`);
        }

        const data = await response.json();
        // The new unified pipeline provides progress updates for both stages
        setProgress(data.progress, data.message, data.estimated_time);

        if (data.status === "SUCCESS") {
          clearInterval(interval);
          const result = data.result;
          
          // Set raw transcription data
          const transcriptionSegments = result.raw_segments || [];
          const rawFormatted = transcriptionSegments.map(
            (seg: { text: string }) => seg.text.trim()
          ).join(' ');
          setTranscription(rawFormatted, transcriptionSegments);

          // Set processed transcription data
          const processedSegments = result.processed_segments || [];
          const processedFormatted = processedSegments.map(
              (seg: { speaker: string, text: string }) => `[${seg.speaker}] ${seg.text.trim()}`
          ).join('\n');
          setProcessedTranscription(processedFormatted, processedSegments);

          setTranscriptionId(result.transcription_id);
          setAudioUrl(`${backendUrl}/api/audio/${result.transcription_id}`);
          setIsLoading(false);
        } else if (data.status === "ERROR") {
          clearInterval(interval);
          setError(data.message);
          setIsLoading(false);
        }
      } catch (error) {
        console.error(error);
        setError("An error occurred while checking task status.");
        clearInterval(interval);
        setIsLoading(false);
      }
    }, 2000);
  };

  const handleSubmit = async () => {
    setIsLoading(true);
    setError("");
    setTranscription("");
    setTranscriptionId(null);
    setProcessedTranscription("");
    setAudioUrl("");
    setProgress(0, "Initiating transcription...");

    const formData = new FormData();
    if (file) {
      formData.append("file", file);
    } else if (url) {
      formData.append("url", url);
    }

    try {
      const response = await fetch(`${backendUrl}/api/transcribe`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to start transcription task.");
      }

      const result = await response.json();
      if (result.task_id) {
        await pollTaskStatus(result.task_id);
      } else {
        throw new Error("Did not receive a task ID from the server.");
      }
    } catch (error: any) {
      console.error(error);
      setError(error.message || "An error occurred during transcription.");
      setIsLoading(false);
    }
  };

  const handleCorrectCompanyName = async () => {
    if (!processedTranscription || !correctCompanyName) return;
    setIsCorrecting(true);
    setError("");
    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
      const response = await fetch(`${backendUrl}/api/transcriptions/correct-company-name`, {
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
      setProcessedTranscription(data.corrected_transcript);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsCorrecting(false);
    }
  };

  const getHistory = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const response = await fetch(`${backendUrl}/api/transcriptions/`);
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to fetch transcription history.");
      }
      const data: TranscriptionItem[] = await response.json();
      setHistory(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [backendUrl, setIsLoading, setError, setHistory, setAudioUrl, setTranscription, setProcessedTranscription, setTranscriptionId]);

  return { handleSubmit, handleCorrectCompanyName, getHistory };
}