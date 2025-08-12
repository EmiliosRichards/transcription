"use client";

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useChatStore } from "@/lib/stores/useChatStore";
import { useChatApi } from "@/lib/hooks/useChatApi";
import { MessageList } from "./chat/MessageList";
import { ChatInput } from "./chat/ChatInput";
import { TranscriptDialog } from "./transcript-dialog";
import { DeleteConfirmationDialog } from "./chat/DeleteConfirmationDialog";

interface SourceDocument {
  customer_id: string;
  full_journey: string;
  call_ids: string;
  distance: number;
}

export interface Message {
  id?: number;
  role: "user" | "assistant";
  content: string;
  source_documents?: SourceDocument[];
}

interface ChatInterfaceProps {
  onNewChat: () => void;
}

export function ChatInterface({ onNewChat }: ChatInterfaceProps) {
  const { messages, sessionId, isLoading } = useChatStore();
  const { handleSendMessage, handleDeleteMessage } = useChatApi();
  const [inputValue, setInputValue] = useState("");
  const [selectedTranscript, setSelectedTranscript] = useState<SourceDocument | null>(null);
  const [messageToDelete, setMessageToDelete] = useState<Message | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const isEmpty = messages.length === 0;

  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTo({
        top: scrollAreaRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages]);

  const onSendMessage = () => {
    handleSendMessage(inputValue, sessionId);
    setInputValue("");
  };

  const onDeleteConfirm = useCallback(() => {
    if (messageToDelete) {
      handleDeleteMessage(messageToDelete, messages, sessionId);
      setMessageToDelete(null);
      onNewChat();
    }
  }, [messageToDelete, handleDeleteMessage, messages, sessionId, onNewChat]);

  const handleWelcomePrompt = useCallback((prompt: string) => {
    handleSendMessage(prompt, sessionId);
  }, [handleSendMessage, sessionId]);

  if (isEmpty) {
    return (
      <div className="flex flex-col h-full items-center justify-center">
        <div className="w-full max-w-4xl">
          <MessageList
            onDeleteMessage={setMessageToDelete}
            onSourceClick={setSelectedTranscript}
            onWelcomePrompt={handleWelcomePrompt}
          />
        </div>
        <div className="w-full max-w-3xl mt-8">
          <ChatInput
            inputValue={inputValue}
            onInputChange={setInputValue}
            onSendMessage={onSendMessage}
            isLoading={isLoading}
          />
        </div>
        <TranscriptDialog
          isOpen={!!selectedTranscript}
          onOpenChange={(isOpen) => !isOpen && setSelectedTranscript(null)}
          transcript={selectedTranscript}
        />
        <DeleteConfirmationDialog
          isOpen={!!messageToDelete}
          onOpenChange={(isOpen) => !isOpen && setMessageToDelete(null)}
          onConfirm={onDeleteConfirm}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <MessageList
        onDeleteMessage={setMessageToDelete}
        onSourceClick={setSelectedTranscript}
        onWelcomePrompt={handleWelcomePrompt}
      />
      <ChatInput
        inputValue={inputValue}
        onInputChange={setInputValue}
        onSendMessage={onSendMessage}
        isLoading={isLoading}
      />
      <TranscriptDialog
        isOpen={!!selectedTranscript}
        onOpenChange={(isOpen) => !isOpen && setSelectedTranscript(null)}
        transcript={selectedTranscript}
      />
      <DeleteConfirmationDialog
        isOpen={!!messageToDelete}
        onOpenChange={(isOpen) => !isOpen && setMessageToDelete(null)}
        onConfirm={onDeleteConfirm}
      />
    </div>
  );
}