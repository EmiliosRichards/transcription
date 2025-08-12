"use client";

import { MessageBubble } from "./MessageBubble";
import { WelcomeScreen } from "../welcome-screen";
import { StatusDisplay } from "./StatusDisplay";
import { Message } from '../chat-interface';
import { useChatStore } from '@/lib/stores/useChatStore';

interface MessageListProps {
  onDeleteMessage: (message: Message) => void;
  onSourceClick: (source: any) => void;
  onWelcomePrompt: (prompt: string) => void;
}

export function MessageList({ onDeleteMessage, onSourceClick, onWelcomePrompt }: MessageListProps) {
  const { messages, isLoading, isStreaming, currentStatus, statusVersion } = useChatStore();
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-6">
        <WelcomeScreen onPromptClick={onWelcomePrompt} />
      </div>
    );
  }

  return (
    <div className="flex-grow overflow-y-auto p-6">
      <div className="space-y-4">
        {messages.map((message, index) => {
          const isLastMessage = index === messages.length - 1;
          return (
            <MessageBubble
              key={message.id}
              message={message}
              isStreaming={isLastMessage && isStreaming}
              onDelete={onDeleteMessage}
              onSourceClick={onSourceClick}
            />
          );
        })}
      </div>
    </div>
  );
}