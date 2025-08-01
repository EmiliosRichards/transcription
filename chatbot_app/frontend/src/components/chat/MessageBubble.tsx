"use client";

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";
import { StatusBox } from "@/components/status-box";
import { SourceDocuments } from "./SourceDocuments";
import { Message } from '../chat-interface';

interface MessageBubbleProps {
  message: Message;
  isLoading: boolean;
  isStreaming: boolean;
  currentStatus: string;
  onDelete: (message: Message) => void;
  onSourceClick: (source: any) => void;
}

export function MessageBubble({ message, isLoading, isStreaming, currentStatus, onDelete, onSourceClick }: MessageBubbleProps) {
  const isLastMessage = false; // This will be determined in the MessageList component

  return (
    <div className={`group flex items-center gap-2 w-full ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      {message.role === "user" && message.id && (
        <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => onDelete(message)}>
          <Trash2 className="h-4 w-4 text-red-500" />
        </Button>
      )}

      <div className={`rounded-lg p-3 ${message.role === "user" ? "bg-gray-200" : "bg-muted"} ${message.role === 'assistant' ? 'animate-fade-in' : ''}`}>
        <div className="space-y-4">
          {isLoading && !isStreaming && isLastMessage ? (
            <StatusBox status={currentStatus} />
          ) : (
            <>
              <div className="prose prose-sm max-w-full">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              </div>
              <SourceDocuments sourceDocuments={message.source_documents || []} onSourceClick={onSourceClick} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}