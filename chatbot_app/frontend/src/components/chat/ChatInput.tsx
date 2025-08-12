"use client";

import { useCallback, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { ArrowUp } from "lucide-react";

interface ChatInputProps {
  inputValue: string;
  onInputChange: (value: string) => void;
  onSendMessage: () => void;
  isLoading: boolean;
}

export function ChatInput({ inputValue, onInputChange, onSendMessage, isLoading }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    const maxHeight = 200; // px, ~10 lines depending on font
    el.style.height = "auto";
    const next = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [inputValue, adjustHeight]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e as any).isComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading && inputValue.trim()) onSendMessage();
    }
  };

  return (
    <div className="p-6">
      <div className="relative">
        <textarea
          ref={textareaRef}
          placeholder="Write a message..."
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          className="w-full resize-none rounded-2xl py-3 pl-4 pr-14 bg-white/80 dark:bg-black/30 backdrop-blur-md border border-white/40 dark:border-white/10 focus:outline-none focus:ring-2 focus:ring-blue-300 dark:focus:ring-blue-700 text-sm leading-6"
        />
        <Button
          size="icon"
          className="absolute right-2 top-[calc(50%-3px)] -translate-y-1/2 rounded-full h-9 w-9"
          onClick={onSendMessage}
          disabled={isLoading || !inputValue.trim()}
          aria-label="Send message"
        >
          <ArrowUp className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}