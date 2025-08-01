"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowUp } from "lucide-react";

interface ChatInputProps {
  inputValue: string;
  onInputChange: (value: string) => void;
  onSendMessage: () => void;
  isLoading: boolean;
}

export function ChatInput({ inputValue, onInputChange, onSendMessage, isLoading }: ChatInputProps) {
  return (
    <div className="p-6">
      <div className="relative">
        <Input
          type="text"
          placeholder="Write a message here..."
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyPress={(e) => e.key === "Enter" && onSendMessage()}
          className="rounded-full py-6 pl-12 pr-20"
        />
        <Button
          size="icon"
          className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full"
          onClick={onSendMessage}
          disabled={isLoading || !inputValue.trim()}
        >
          <ArrowUp className="h-5 w-5" />
        </Button>
      </div>
    </div>
  );
}