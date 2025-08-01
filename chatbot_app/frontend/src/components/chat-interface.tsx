"use client";

"use client";

import { useState, useEffect, useRef } from "react";
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
  const { messages, sessionId, isLoading, isStreaming, currentStatus } = useChatStore();
  const { handleSendMessage, handleDeleteMessage } = useChatApi();
  const [inputValue, setInputValue] = useState("");
  const [selectedTranscript, setSelectedTranscript] = useState<SourceDocument | null>(null);
  const [messageToDelete, setMessageToDelete] = useState<Message | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

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

  const onDeleteConfirm = () => {
    if (messageToDelete) {
      handleDeleteMessage(messageToDelete, messages, sessionId);
      setMessageToDelete(null);
      onNewChat();
    }
  };

  return (
    <div className="flex flex-col h-full">
      <MessageList
        messages={messages}
        isLoading={isLoading}
        isStreaming={isStreaming}
        currentStatus={currentStatus}
        onDeleteMessage={setMessageToDelete}
        onSourceClick={setSelectedTranscript}
        onWelcomePrompt={(prompt) => {
          setInputValue(prompt);
          handleSendMessage(prompt, sessionId);
        }}
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