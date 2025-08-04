"use client";

import React, { memo, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";
import { SourceDocuments } from "./SourceDocuments";
import { Message } from '../chat-interface';
import { useChatStore } from '@/lib/stores/useChatStore';
import { StatusDisplay } from './StatusDisplay';

interface MessageBubbleProps {
  message: Message;
  isStreaming: boolean;
  onDelete: (message: Message) => void;
  onSourceClick: (source: any) => void;
}

const StreamingCursor = () => <span className="animate-pulse">▍</span>;

const MessageBubbleComponent = ({ message, isStreaming, onDelete, onSourceClick }: MessageBubbleProps) => {
  const { isLoading, currentStatus } = useChatStore();
  const bubbleRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (bubbleRef.current) {
      bubbleRef.current.classList.add('animate-fade-in');
    }
  }, []);

  const showStatus = isLoading && message.role === 'assistant' && !message.content;

  return (
    <div className={`group flex items-start gap-2 w-full ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      {message.role === "user" && message.id && (
        <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => onDelete(message)}>
          <Trash2 className="h-4 w-4 text-red-500" />
        </Button>
      )}

      <div ref={bubbleRef} className={`rounded-lg p-3 ${message.role === "user" ? "bg-gray-200" : "bg-muted"}`}>
        {showStatus ? (
          <StatusDisplay currentStatus={currentStatus} />
        ) : (
          <div className="space-y-4">
            <div className="prose prose-sm max-w-full">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
              {isStreaming && <StreamingCursor />}
            </div>
            {message.source_documents && message.source_documents.length > 0 && (
              <SourceDocuments sourceDocuments={message.source_documents} onSourceClick={onSourceClick} />
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export const MessageBubble = memo(MessageBubbleComponent);