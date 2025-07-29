"use client";

import { LayoutDashboard, Plus, Search } from "lucide-react";
import Link from "next/link";
import { Button } from "./ui/button";
import { Message } from "./chat-interface";

interface SidebarProps {
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
}

export function Sidebar({ setMessages }: SidebarProps) {
  return (
    <aside className="fixed top-0 left-0 h-full flex flex-col w-64 p-4 bg-white/30 backdrop-blur-lg border-r">
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-lg bg-gradient-to-r from-blue-900 to-blue-500 text-transparent bg-clip-text">Chats</h2>
        <Button variant="ghost" size="icon">
          <Search className="h-4 w-4" />
        </Button>
      </div>
      <Button variant="ghost" className="w-full justify-start bg-gray-200 text-gray-800 font-normal" onClick={() => setMessages([])}>
        <Plus className="mr-2 h-4 w-4" />
        New Chat
      </Button>
      <Link href="/dashboard" className="mt-4">
        <Button variant="ghost" className="w-full justify-start font-normal">
          <LayoutDashboard className="mr-2 h-4 w-4" />
          Dashboard
        </Button>
      </Link>
    </aside>
  );
}