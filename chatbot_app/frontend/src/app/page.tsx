"use client";

import { useState } from "react";
import { ChatInterface } from "@/components/chat-interface";
import { Sidebar } from "@/components/sidebar";
import { useChatStore } from "@/lib/stores/useChatStore";

export default function Home() {
  const { setMessages, setSessionId, sessionId } = useChatStore();
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <main className="flex min-h-screen w-full">
      <Sidebar
        refreshKey={refreshKey}
        activeSessionId={sessionId}
      />
      <div className="flex flex-col w-full items-center justify-center p-8 ml-64">
        <div className="w-full max-w-4xl h-full bg-card rounded-2xl shadow-lg border">
          <ChatInterface
            onNewChat={() => setRefreshKey(prev => prev + 1)}
          />
        </div>
      </div>
    </main>
  );
}
