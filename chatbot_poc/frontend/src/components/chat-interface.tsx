"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { createParser } from 'eventsource-parser';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface SourceDocument {
  customer_id: string;
  full_journey: string;
  call_ids: string;
  distance: number;
}

export interface Message {
  sender: "user" | "bot";
  text?: string;
  llm_response?: string;
  source_documents?: SourceDocument[];
}

import { WelcomeScreen } from "./welcome-screen";
import { ArrowUp } from "lucide-react";
import { TranscriptDialog } from "./transcript-dialog";
import { StatusBox } from "./status-box";

interface ChatInterfaceProps {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
}

export function ChatInterface({ messages, setMessages }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedTranscript, setSelectedTranscript] = useState<SourceDocument | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTo({
        top: scrollAreaRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages]);

  const handleSendMessage = async (query?: string) => {
    const messageText = query || inputValue;
    if (messageText.trim() && !isLoading) {
      const userMessage: Message = { sender: "user", text: messageText };
      setMessages(prevMessages => [...prevMessages, userMessage]);
      setInputValue("");
      setIsLoading(true);
      setIsStreaming(false);

      // Add a placeholder for the bot's response
      const botMessagePlaceholder: Message = { sender: "bot", llm_response: "", source_documents: [] };
      setMessages(prevMessages => [...prevMessages, botMessagePlaceholder]);

      try {
        const response = await fetch("http://localhost:8000/api/search", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ query: messageText, stream: true }),
        });

        if (!response.ok || !response.body) {
          throw new Error("Network response was not ok");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const processStream = async () => {
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || ''; // Keep the last partial message

            for (const line of lines) {
              const eventMatch = line.match(/event: (.*)/);
              const dataMatch = line.match(/data: (.*)/);

              if (eventMatch && dataMatch) {
                const event = eventMatch[1];
                const data = dataMatch[1];

                try {
                  if (event === 'sources') {
                    const sources = JSON.parse(data);
                    setMessages(prev => prev.map((msg, i) => i === prev.length - 1 ? { ...msg, source_documents: sources } : msg));
                  } else if (event === 'llm_response_chunk') {
                    if (!isStreaming) setIsStreaming(true);
                    const chunk = JSON.parse(data);
                    setMessages(prev => prev.map((msg, i) => i === prev.length - 1 ? { ...msg, llm_response: (msg.llm_response || "") + chunk.token } : msg));
                  } else if (event === 'stream_end') {
                    setIsLoading(false);
                    setIsStreaming(false);
                  }
                } catch (e) {
                  console.error("Error parsing SSE data:", e);
                }
              }
            }
          }
        };

        processStream();

      } catch (error) {
        console.error("Failed to fetch search results:", error);
        setMessages(prev => prev.slice(0, -1)); // Remove placeholder
        const errorMessage: Message = { sender: "bot", text: "Sorry, I had trouble getting results. Please try again." };
        setMessages(prevMessages => [...prevMessages, errorMessage]);
        setIsLoading(false);
        setIsStreaming(false);
      }
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-grow overflow-y-auto p-6">
        {messages.length === 0 ? (
          <WelcomeScreen onPromptClick={handleSendMessage} />
        ) : (
          <div className="space-y-4">
            {messages.map((message, index) => (
              <div key={index} className={`flex items-start gap-4 ${message.sender === "user" ? "justify-end" : ""}`}>
                {message.sender === "bot" && (
                  <Avatar>
                    <AvatarFallback>B</AvatarFallback>
                  </Avatar>
                )}
                <div className={`rounded-lg p-3 ${message.sender === "user" ? "bg-gray-200" : "bg-muted"} ${message.sender === 'bot' ? 'animate-fade-in' : ''}`}>
                  {message.text ? (
                    <p className="text-gray-800 font-normal">{message.text}</p>
                  ) : (
                    <div className="space-y-4">
                      {isLoading && !isStreaming && index === messages.length - 1 ? (
                        <StatusBox />
                      ) : (
                        <>
                          <div className="prose">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {message.llm_response}
                            </ReactMarkdown>
                          </div>
                          {message.source_documents && message.source_documents.length > 0 && (
                            <div>
                              <details>
                                <summary className="text-sm font-semibold cursor-pointer">
                                  View Sources ({message.source_documents.length})
                                </summary>
                                <div className="mt-2 space-y-2">
                                  {message.source_documents.map((doc) => (
                                    <div key={doc.customer_id} className="p-2 border rounded bg-background/50 cursor-pointer hover:bg-muted" onClick={() => setSelectedTranscript(doc)}>
                                      <p className="text-sm font-bold">Customer ID: {doc.customer_id}</p>
                                      <p className="text-xs text-muted-foreground">Call IDs: {doc.call_ids}</p>
                                      <p className="text-sm mt-1 italic">"{doc.full_journey.substring(0, 200)}..."</p>
                                    </div>
                                  ))}
                                </div>
                              </details>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
                {message.sender === "user" && (
                  <Avatar>
                    <AvatarFallback>U</AvatarFallback>
                  </Avatar>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="p-6">
        <div className="relative">
          <Input
            type="text"
            placeholder="Write a message here..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
            className="rounded-full py-6 pl-12 pr-20"
          />
          <Button
            size="icon"
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full"
            onClick={() => handleSendMessage()}
            disabled={isLoading || !inputValue.trim()}
          >
            <ArrowUp className="h-5 w-5" />
          </Button>
        </div>
      </div>
      <TranscriptDialog
        isOpen={!!selectedTranscript}
        onOpenChange={(isOpen) => !isOpen && setSelectedTranscript(null)}
        transcript={selectedTranscript}
      />
    </div>
  );
}