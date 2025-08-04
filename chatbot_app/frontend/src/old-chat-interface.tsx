"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Trash2 } from "lucide-react";
import { createParser } from 'eventsource-parser';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface SourceDocument {
  customer_id: string;
  full_journey: string;
  call_ids: string;
  distance: number;
}

export interface Message {
  id?: number; // Add id to the message interface
  role: "user" | "assistant";
  content: string;
  source_documents?: SourceDocument[];
}

import { WelcomeScreen } from "@/components/welcome-screen";
import { ArrowUp } from "lucide-react";
import { TranscriptDialog } from "@/components/transcript-dialog";
import { StatusBox } from "@/components/status-box";

interface ChatInterfaceProps {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  sessionId: string | null;
  setSessionId: React.Dispatch<React.SetStateAction<string | null>>;
  onNewChat: () => void;
}

export function ChatInterface({ messages, setMessages, sessionId, setSessionId, onNewChat }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [selectedTranscript, setSelectedTranscript] = useState<SourceDocument | null>(null);
  const [messageToDelete, setMessageToDelete] = useState<Message | null>(null);
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
      console.log("Sending message:", messageText);
      const userMessage: Message = { role: "user", content: messageText };
      const newMessages = [...messages, userMessage];
      setMessages(newMessages);
      setInputValue("");
      setIsLoading(true);

      // Add a placeholder for the bot's response
      setMessages(prev => [...prev, { role: "assistant", content: "", source_documents: [] }]);

      try {
        console.log("Fetching from /api/search");
        const response = await fetch("/api/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: messageText,
            stream: true,
            session_id: sessionId,
          }),
        });

        if (!response.ok || !response.body) {
          throw new Error("Network response was not ok");
        }
        console.log("Response OK, processing stream");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const processStream = async () => {
          while (true) {
            const { value, done } = await reader.read();
            if (done) {
              console.log("Stream finished");
              setIsLoading(false);
              break;
            }

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
                console.log("Received SSE event:", { event, data });

                if (event === 'user_message_saved') {
                  if (data.session_id && !sessionId) {
                    setSessionId(data.session_id);
                    onNewChat();
                  }
                  setMessages(prev => {
                    const newMessages = [...prev];
                    const userMessageIndex = newMessages.findLastIndex(m => m.role === 'user');
                    if (userMessageIndex !== -1) {
                      newMessages[userMessageIndex].id = data.user_message_id;
                    }
                    return newMessages;
                  });
                } else if (event === 'sources') {
                  setMessages(prev => prev.map((msg, i) => i === prev.length - 1 ? { ...msg, source_documents: data.sources } : msg));
                } else if (event === 'llm_response_chunk') {
                  setMessages(prev => prev.map((msg, i) => i === prev.length - 1 ? { ...msg, content: (msg.content || "") + data.token } : msg));
                } else if (event === 'error') {
                   console.error("Received error event:", data.message);
                   setMessages(prev => prev.map((msg, i) => i === prev.length - 1 ? { ...msg, content: `Error: ${data.message}` } : msg));
                   setIsLoading(false);
                   return;
                } else if (event === 'stream_end') {
                  const finalData = JSON.parse(dataString);
                  if (finalData.assistant_message_id) {
                    setMessages(prev => {
                      const newMessages = [...prev];
                      const assistantMessageIndex = newMessages.findLastIndex(m => m.role === 'assistant');
                      if (assistantMessageIndex !== -1) {
                        newMessages[assistantMessageIndex].id = finalData.assistant_message_id;
                      }
                      return newMessages;
                    });
                  }
                  setIsLoading(false);
                  return;
                }
              } catch (e) {
                console.error("Error parsing SSE data:", e, "Raw line:", line);
              }
            }
          }
        };

        await processStream();

      } catch (error) {
        console.error("Failed to fetch search results:", error);
        const message = error instanceof Error ? error.message : "An unknown error occurred.";
        setMessages(prev => prev.map((msg, i) => i === prev.length - 1 ? { ...msg, content: `Failed to fetch search results: ${message}` } : msg));
        setIsLoading(false);
      }
    }
  };

  const handleDeleteMessage = async () => {
    if (!messageToDelete?.id) return;

    try {
      const response = await fetch(`/api/chats/messages/${messageToDelete.id}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete message');
      }

      const messageIndex = messages.findIndex(msg => msg.id === messageToDelete.id);
      if (messageIndex !== -1) {
        // Check if it's the first message in the session
        const isFirstMessage = messages[messageIndex].id === messages[0].id;

        if (isFirstMessage) {
            // If the first message is deleted, the whole session is gone.
            setMessages([]);
            setSessionId(null);
            onNewChat(); // To refresh sidebar
        } else {
            // Remove this message and all subsequent messages
            setMessages(prev => prev.slice(0, messageIndex));
        }
      }
    } catch (error) {
      console.error("Error deleting message:", error);
      // Optionally, show an error to the user
    } finally {
      setMessageToDelete(null);
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
              <div key={index} className={`group flex items-center gap-2 w-full ${message.role === "user" ? "justify-end" : "justify-start"}`}>

                {message.role === "user" && message.id && (
                  <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => setMessageToDelete(message)}>
                    <Trash2 className="h-4 w-4 text-red-500" />
                  </Button>
                )}

                <div className={`rounded-lg p-3 ${message.role === "user" ? "bg-gray-200" : "bg-muted"} ${message.role === 'assistant' ? 'animate-fade-in' : ''}`}>
                  <div className="space-y-4">
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
                  </div>
                </div>


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
        onOpenChange={(isOpen: boolean) => !isOpen && setSelectedTranscript(null)}
        transcript={selectedTranscript}
      />
      <AlertDialog open={!!messageToDelete} onOpenChange={(open) => !open && setMessageToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete this message and all subsequent messages in this conversation. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteMessage}
              className="bg-red-500 hover:bg-red-600"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}