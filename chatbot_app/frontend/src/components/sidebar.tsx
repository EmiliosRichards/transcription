"use client";

import { useEffect, useState, useCallback } from "react";
import { LayoutDashboard, Plus, Search, Trash2 } from "lucide-react";
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
}

interface ChatSessionInfo {
  session_id: string;
  start_time: string;
  initial_message: string;
}

export function Sidebar({ refreshKey, activeSessionId }: SidebarProps) {
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
    <aside className="fixed top-0 left-0 h-full flex flex-col w-64 p-4 bg-sidebar border-r">
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg bg-gradient-to-r from-blue-900 to-blue-500 text-transparent bg-clip-text">
            Chats
          </h2>
          <Button variant="ghost" size="icon" onClick={() => setIsSearching(!isSearching)}>
            <Search className="h-4 w-4" />
          </Button>
        </div>
        {isSearching && (
          <Input
            placeholder="Search chats..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="mb-4"
          />
        )}
        <Button
          variant="ghost"
          className="w-full justify-start bg-gray-200 text-gray-800 font-normal"
          onClick={() => {
            setMessages([]);
            setSessionId(null);
          }}
        >
          <Plus className="mr-2 h-4 w-4" />
          New Chat
        </Button>
        <Link href="/dashboard" className="mt-4 block">
          <Button variant="ghost" className="w-full justify-start font-normal">
            <LayoutDashboard className="mr-2 h-4 w-4" />
            Dashboard
          </Button>
        </Link>
        <Link href="/transcribe" className="mt-2 block">
          <Button variant="ghost" className="w-full justify-start font-normal">
            <LayoutDashboard className="mr-2 h-4 w-4" />
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
                    <p className="truncate">{session.initial_message}</p>
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