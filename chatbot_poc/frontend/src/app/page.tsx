"use client";

import { useState } from "react";
import { ChatInterface } from "@/components/chat-interface";
import { Sidebar } from "@/components/sidebar";
import { Message } from "@/components/chat-interface";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);

  return (
    <main className="flex min-h-screen w-full">
      <Sidebar setMessages={setMessages} />
      <div className="flex flex-col w-full items-center justify-center p-8 ml-64">
        <div className="w-full max-w-4xl h-full bg-white/50 backdrop-blur-lg rounded-2xl shadow-lg border">
          <ChatInterface messages={messages} setMessages={setMessages} />
        </div>
      </div>
    </main>
  );
}
