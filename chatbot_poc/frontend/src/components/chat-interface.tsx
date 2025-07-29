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
  role: "user" | "assistant";
  content: string;
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
  const [currentStatus, setCurrentStatus] = useState("Thinking...");
  const [selectedTranscript, setSelectedTranscript] = useState<SourceDocument | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

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
      const userMessage: Message = { role: "user", content: messageText };
      setMessages(prev => [...prev, userMessage]);
      setInputValue("");
      setIsLoading(true);
      setIsStreaming(false);
      setCurrentStatus("Sending request...");

      // Add a placeholder for the bot's response
      const botMessagePlaceholder: Message = { role: "assistant", content: "", source_documents: [] };
      setMessages(prev => [...prev, botMessagePlaceholder]);

      // Set a timeout for the request
      timeoutRef.current = setTimeout(() => {
        handleError("The request timed out. Please try again.");
      }, 30000); // 30 seconds

      const handleError = (errorMessage: string) => {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        setMessages(prev => {
          const lastMessage = prev[prev.length - 1];
          if (lastMessage?.role === 'assistant' && !lastMessage.content) {
            return [...prev.slice(0, -1), { role: 'assistant', content: errorMessage }];
          }
          return [...prev, { role: 'assistant', content: errorMessage }];
        });
        setIsLoading(false);
        setIsStreaming(false);
      };

      try {
        // Prepare history from the state *before* the new user message and placeholder were added
        const history = messages.slice(-6).map(({ role, content }) => ({ role, content }));

        const response = await fetch("http://localhost:8000/api/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: messageText,
            stream: true,
            history: history.slice(-6) // Send the last 6 messages
          }),
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
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (!line.startsWith('event:')) continue;
              
              const event = line.match(/event: (.*)/)?.[1];
              const dataString = line.match(/data: (.*)/)?.[1];
              if (!event || !dataString) continue;

              try {
                const data = JSON.parse(dataString);

                if (event === 'status_update') {
                  setCurrentStatus(data.status);
                } else if (event === 'sources') {
                  setMessages(prev => prev.map((msg, i) => i === prev.length - 1 ? { ...msg, source_documents: data.sources } : msg));
                } else if (event === 'llm_response_chunk') {
                  if (!isStreaming) {
                    setIsStreaming(true);
                    setCurrentStatus("Generating answer..."); // Final status before text appears
                  }
                  setMessages(prev => prev.map((msg, i) => i === prev.length - 1 ? { ...msg, content: (msg.content || "") + data.token } : msg));
                } else if (event === 'error') {
                  handleError(data.message || "An unknown error occurred.");
                  return; // Stop processing on error
                } else if (event === 'stream_end') {
                  if (timeoutRef.current) clearTimeout(timeoutRef.current);
                  setIsLoading(false);
                  setIsStreaming(false);
                  return; // End of stream
                }
              } catch (e) {
                console.error("Error parsing SSE data:", e);
              }
            }
          }
        };

        await processStream();

      } catch (error) {
        const message = error instanceof Error ? error.message : "An unknown error occurred.";
        handleError(`Failed to fetch search results: ${message}`);
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
              <div key={index} className={`flex items-start gap-4 ${message.role === "user" ? "justify-end" : ""}`}>
                {message.role === "assistant" && (
                  <Avatar>
                    <AvatarFallback>B</AvatarFallback>
                  </Avatar>
                )}
                <div className={`rounded-lg p-3 ${message.role === "user" ? "bg-gray-200" : "bg-muted"} ${message.role === 'assistant' ? 'animate-fade-in' : ''}`}>
                  <div className="space-y-4">
                    {isLoading && !isStreaming && index === messages.length - 1 && !message.content ? (
                      <StatusBox status={currentStatus} />
                    ) : (
                      <>
                        <div className="prose prose-sm max-w-full">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {message.content}
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
                </div>
                {message.role === "user" && (
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