"use client";

import { useEffect, useState, useCallback } from "react";
import { BarChart3, Mic, Search, Trash2, ChevronLeft, PencilLine } from "lucide-react";
import Link from "next/link";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Message } from "./chat-interface";
import { ModeToggle } from "./theme-toggle";
import { ScrollArea } from "./ui/scroll-area";
import { useChatStore } from "@/lib/stores/useChatStore";
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
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";

interface SidebarProps {
  refreshKey: number;
  activeSessionId: string | null;
  isOpen: boolean;
  onToggle: () => void;
  isOverlay?: boolean;
}

interface ChatSessionInfo {
  session_id: string;
  start_time: string;
  initial_message: string;
}

export function Sidebar({ refreshKey, activeSessionId, isOpen, onToggle, isOverlay = false }: SidebarProps) {
  const { setMessages, setSessionId } = useChatStore();
  const [chatSessions, setChatSessions] = useState<ChatSessionInfo[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);

  const fetchChats = useCallback(async () => {
    try {
      const response = await fetch("/api/chats");
      if (response.ok) {
        const data = await response.json();
        setChatSessions(data);
      }
    } catch (error) {
      console.error("Failed to fetch chat sessions:", error);
    }
  }, []);

  useEffect(() => {
    fetchChats();
  }, [refreshKey, fetchChats]);

  const filteredChats = chatSessions.filter((session) =>
    session.initial_message.toLowerCase().includes(searchTerm.toLowerCase())
  );

  async function loadChat(sessionId: string) {
    try {
      const response = await fetch(`/api/chats/${sessionId}`);
      if (response.ok) {
        const data = await response.json();
        const formattedMessages: Message[] = data.map((msg: { id: number; role: "user" | "assistant"; content: string }) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
        }));
        setMessages(formattedMessages);
        setSessionId(sessionId);
      } else {
        console.error("Failed to fetch chat session:", await response.text());
      }
    } catch (error) {
      console.error("Failed to fetch chat session:", error);
    }
  }

  async function handleDeleteChat(sessionId: string) {
    try {
      const response = await fetch(`/api/chats/${sessionId}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        fetchChats();
        if (activeSessionId === sessionId) {
          setMessages([]);
          setSessionId(null);
        }
      } else {
        console.error("Failed to delete chat session:", await response.text());
      }
    } catch (error) {
      console.error("Failed to delete chat session:", error);
    }
  }

  return (
    <aside
      className={
        `fixed top-0 left-0 h-full flex flex-col w-64 p-4 border-r transform transition-transform duration-300 z-40 ` +
        (isOverlay
          ? "bg-white dark:bg-gray-950 shadow-xl"
          : "bg-transparent backdrop-blur-sm") +
        (isOpen ? " translate-x-0" : " -translate-x-full")
      }
    >
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg bg-gradient-to-r from-blue-900 to-blue-500 dark:from-sky-300 dark:to-blue-200 text-transparent bg-clip-text">
            Chats
          </h2>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" onClick={onToggle} aria-label="Collapse sidebar">
              <ChevronLeft className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {isSearching && (
          <Input
            placeholder="Search chats..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="mb-4"
          />
        )}
        <div className="space-y-2">
          <Button
            variant="ghost"
            className="w-full justify-start font-normal bg-gray-200 text-gray-800 hover:bg-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
            onClick={() => {
              setMessages([]);
              setSessionId(null);
            }}
          >
            <PencilLine className="mr-2 h-4 w-4" />
            New chat
          </Button>

          <Button
            variant="ghost"
            className="w-full justify-start font-normal"
            onClick={() => setIsSearching((v) => !v)}
          >
            <Search className="mr-2 h-4 w-4" />
            Search chats
          </Button>
        </div>
        <Link href="/dashboard" className="mt-4 block">
          <Button variant="ghost" className="w-full justify-start font-normal">
            <BarChart3 className="mr-2 h-4 w-4" />
            Data Analytics
          </Button>
        </Link>
        <Link href="/transcribe" className="mt-2 block">
          <Button variant="ghost" className="w-full justify-start font-normal">
            <Mic className="mr-2 h-4 w-4" />
            Transcribe
          </Button>
        </Link>
      </div>

      <div className="flex-1 flex flex-col mt-4 overflow-hidden">
        <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-2">Recent Chats</h3>
        <ScrollArea className="flex-1">
          <div className="space-y-2">
            {filteredChats.map((session) => (
              <ContextMenu key={session.session_id}>
                <ContextMenuTrigger>
                  <Button
                    variant={session.session_id === activeSessionId ? "secondary" : "ghost"}
                    className="w-full justify-start font-normal text-sm h-auto py-2 transition-colors duration-200 text-left"
                    onClick={() => loadChat(session.session_id)}
                  >
                    <span className="relative flex-1 min-w-0 overflow-hidden fade-right-overlay">
                      <span className="block w-full whitespace-nowrap overflow-hidden pr-3">{session.initial_message}</span>
                    </span>
                  </Button>
                </ContextMenuTrigger>
                <ContextMenuContent>
                  <ContextMenuItem
                    className="text-red-500"
                    onSelect={() => setDeletingSessionId(session.session_id)}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete Chat
                  </ContextMenuItem>
                </ContextMenuContent>
              </ContextMenu>
            ))}
          </div>
        </ScrollArea>
      </div>

      <div className="mt-auto flex justify-end">
        <ModeToggle />
      </div>

      <AlertDialog open={!!deletingSessionId} onOpenChange={(open) => !open && setDeletingSessionId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete this chat history. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deletingSessionId) {
                  handleDeleteChat(deletingSessionId);
                }
              }}
              className="bg-red-500 hover:bg-red-600"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  );
}