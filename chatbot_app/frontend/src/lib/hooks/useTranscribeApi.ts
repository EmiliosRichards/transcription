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
    setIsProcessing,
    setIsCorrecting,
    setError,
  } = useTranscribeStore();

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
      setProcessedTranscription(data.corrected_transcript);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsCorrecting(false);
    }
  };

  return { handleSubmit, handlePostProcess, handleCorrectCompanyName };
}