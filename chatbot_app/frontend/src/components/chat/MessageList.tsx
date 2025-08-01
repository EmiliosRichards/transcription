"use client";

import { MessageBubble } from "./MessageBubble";
import { WelcomeScreen } from "../welcome-screen";
import { Message } from '../chat-interface';

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  currentStatus: string;
  onDeleteMessage: (message: Message) => void;
  onSourceClick: (source: any) => void;
  onWelcomePrompt: (prompt: string) => void;
}

export function MessageList({ messages, isLoading, isStreaming, currentStatus, onDeleteMessage, onSourceClick, onWelcomePrompt }: MessageListProps) {
  if (messages.length === 0) {
    return <WelcomeScreen onPromptClick={onWelcomePrompt} />;
  }

  return (
    <div className="flex-grow overflow-y-auto p-6">
      <div className="space-y-4">
        {messages.map((message, index) => (
          <MessageBubble
            key={index}
            message={message}
            isLoading={isLoading && index === messages.length - 1}
            isStreaming={isStreaming && index === messages.length - 1}
            currentStatus={currentStatus}
            onDelete={onDeleteMessage}
            onSourceClick={onSourceClick}
          />
        ))}
      </div>
    </div>
  );
}