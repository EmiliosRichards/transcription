import { useTranscribeStore, TranscriptionItem } from '../stores/useTranscribeStore';
import { useCallback } from 'react';

export function useTranscribeApi() {
  const {
    file,
    url,
    transcriptionId,
    processedTranscription,
    correctCompanyName,
    setIsLoading,
    setTranscription,
    setTranscriptionId,
    setProcessedTranscription,
    setAudioUrl,
    fetchAndSetAudioUrl,
    setIsCorrecting,
    setError,
    startCinematicExperience,
    advanceCinematicStage,
    setHistory,
  } = useTranscribeStore();

  const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

  const pollTaskStatus = async (taskId: string) => {
    let isRequestInFlight = false;
    const interval = setInterval(async () => {
      if (isRequestInFlight) {
        return; // Avoid overlapping polls
      }
      isRequestInFlight = true;
      const { cinematicStage } = useTranscribeStore.getState();
      let rawTranscriptReceived = false;

      try {
        const response = await fetch(`${backendUrl}/api/tasks/${taskId}`);
        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: response.statusText }));
          throw new Error(`Failed to get task status: ${err.detail}`);
        }

        const data = await response.json();

        // Reflect backend progress/message when available
        if (typeof data.progress === 'number') {
          useTranscribeStore.setState({ progress: data.progress });
        }
        if (typeof data.message === 'string' && data.message.length > 0) {
          useTranscribeStore.setState({ progressMessage: data.message });
        }

        const result = data.result;
        // Consider RAW ready if raw_segments exist and we are still in TRANSCRIBING stage
        const shouldIngestRaw = (
          cinematicStage === 'TRANSCRIBING' &&
          result && Array.isArray(result.raw_segments) &&
          useTranscribeStore.getState().transcriptionSegments.length === 0
        );
        if (shouldIngestRaw) {
          rawTranscriptReceived = true;
          const transcriptionSegments = result.raw_segments || [];
          const rawFormatted = transcriptionSegments.map(
            (seg: { text: string }) => seg.text.trim()
          ).join(' ');
          setTranscription(rawFormatted, transcriptionSegments);
          setTranscriptionId(result.transcription_id);
          if (result.transcription_id) {
            fetchAndSetAudioUrl(result.transcription_id);
          }
      advanceCinematicStage();
        }

        // If the backend now includes a transcription_id and we don't have one yet, set it and fetch audio
        if (
          result && result.transcription_id && !useTranscribeStore.getState().transcriptionId
        ) {
          setTranscriptionId(result.transcription_id);
          fetchAndSetAudioUrl(result.transcription_id);
        }

        if (data.status === "SUCCESS") {
          const result = data.result;
          // Defensive: ensure raw transcript is set even if intermediate event was missed
          if (result.raw_segments && useTranscribeStore.getState().transcriptionSegments.length === 0) {
            const rawFormatted = result.raw_segments.map((seg: { text: string }) => seg.text.trim()).join(' ');
            setTranscription(rawFormatted, result.raw_segments);
          }
          // Ensure audio is available once the transcription_id exists
          if (result.transcription_id && !useTranscribeStore.getState().transcriptionId) {
            setTranscriptionId(result.transcription_id);
            fetchAndSetAudioUrl(result.transcription_id);
          }
          const processedSegments = result.processed_segments || [];
          const processedFormatted = processedSegments.map(
              (seg: { speaker: string, text: string }) => `${seg.speaker.replace(/\[|\]/g, '')}: ${seg.text.trim()}`
          ).join('\n');
          setProcessedTranscription(processedFormatted, processedSegments);
          // Keep success message visible for a moment before hiding loader
          useTranscribeStore.setState({ progress: 100, progressMessage: 'Transcription completed successfully.' });
          setTimeout(() => {
            setIsLoading(false);
            useTranscribeStore.setState({ cinematicStage: 'DONE' });
            clearInterval(interval);
          }, 1200);
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
      } finally {
        isRequestInFlight = false;
      }
    }, 500);
  };

  const handleSubmit = async () => {
    startCinematicExperience();

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