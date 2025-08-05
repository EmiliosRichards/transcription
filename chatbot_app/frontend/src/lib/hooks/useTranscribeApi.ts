import { useTranscribeStore } from '../stores/useTranscribeStore';

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
  } = useTranscribeStore();

  const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

  const pollTaskStatus = async (taskId: string, isProcessing: boolean = false) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${backendUrl}/api/transcribe/status/${taskId}`);
        if (!response.ok) {
          // Stop polling on non-2xx responses
          throw new Error(`Failed to get task status: ${response.statusText}`);
        }

        const data = await response.json();
        if (isProcessing) {
          setProcessingProgress(data.progress, data.message);
        } else {
          setProgress(data.progress, data.message, data.estimated_time);
        }

        if (data.status === "SUCCESS") {
          clearInterval(interval);
          if (isProcessing) {
            setProcessedTranscription(data.result.processed_transcription);
            setIsProcessing(false);
          } else {
            // The backend now returns segments. We need to format them for display.
            if (data.result.transcription_segments) {
              const formatted = data.result.transcription_segments.map(
                (seg: { text: string }) => seg.text.trim()
              ).join(' ');
              setTranscription(formatted);
            } else {
              // Fallback for any old data or unexpected format
              setTranscription(data.result.transcription || "Processing complete, but no text was returned.");
            }
            setTranscriptionId(data.result.transcription_id);
            setAudioUrl(`${backendUrl}/api/audio/${data.result.transcription_id}`);
            setIsLoading(false);
          }
        } else if (data.status === "ERROR") {
          clearInterval(interval);
          setError(data.message);
          setIsLoading(false);
          setIsProcessing(false);
        }
      } catch (error) {
        console.error(error);
        setError("An error occurred while checking task status.");
        clearInterval(interval);
        setIsLoading(false);
        setIsProcessing(false);
      }
    }, 2000); // Poll every 2 seconds
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

  const handlePostProcess = async () => {
    if (!transcriptionId) return;
    setIsProcessing(true);
    setError("");
    try {
      const response = await fetch(`${backendUrl}/api/post-process-transcription`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ transcription_id: transcriptionId }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to start post-processing task.");
      }

      const result = await response.json();
      if (result.task_id) {
        await pollTaskStatus(result.task_id, true);
      } else {
        throw new Error("Did not receive a task ID from the server for post-processing.");
      }
    } catch (err: any) {
      setError(err.message);
      setIsProcessing(false); // Ensure this is reset on error
    }
  };

  const handleCorrectCompanyName = async () => {
    if (!processedTranscription || !correctCompanyName) return;
    setIsCorrecting(true);
    setError("");
    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
      const response = await fetch(`${backendUrl}/api/correct-company-name`, {
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

  return { handleSubmit, handlePostProcess, handleCorrectCompanyName };
}