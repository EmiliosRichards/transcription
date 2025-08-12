"use client";

import { useEffect, useState } from "react";
import { ChatInterface } from "@/components/chat-interface";
import { Sidebar } from "@/components/sidebar";
import { useChatStore } from "@/lib/stores/useChatStore";
import { Button } from "@/components/ui/button";
import { Menu } from "lucide-react";

export default function Home() {
  const { setMessages, setSessionId, sessionId } = useChatStore();
  const [refreshKey, setRefreshKey] = useState(0);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isNarrow, setIsNarrow] = useState(false);

  // Track viewport width and auto-close sidebar on narrow screens
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1024px)"); // Tailwind lg breakpoint
    const handleChange = () => {
      const narrow = media.matches;
      setIsNarrow(narrow);
      if (narrow) {
        setIsSidebarOpen(false);
      }
    };
    handleChange();
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  // Prevent body scroll when sidebar overlays (narrow + open)
  useEffect(() => {
    if (isNarrow && isSidebarOpen) {
      const previous = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = previous;
      };
    }
  }, [isNarrow, isSidebarOpen]);

  return (
    <main className="flex min-h-screen w-full">
      <Sidebar
        refreshKey={refreshKey}
        activeSessionId={sessionId}
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen((v) => !v)}
        isOverlay={isNarrow}
      />

      {/* Overlay for narrow screens when sidebar is open */}
      {isNarrow && isSidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/15 backdrop-blur-[1.5px]"
          onClick={() => setIsSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Floating toggle shows only when sidebar is closed */}
      {!isSidebarOpen && (
        <Button
          variant="ghost"
          size="icon"
          className="fixed top-4 left-4 z-50 rounded-full shadow-sm bg-white/70 dark:bg-gray-900/60 backdrop-blur hover:bg-white/90 dark:hover:bg-gray-900"
          onClick={() => setIsSidebarOpen(true)}
          aria-label="Open sidebar"
        >
          <Menu className="h-5 w-5" />
        </Button>
      )}

      <div className={`flex flex-col w-full items-center justify-center p-8 transition-[margin] duration-300 ${!isNarrow && isSidebarOpen ? "ml-64" : "ml-0"}`}>
        <div className="w-full max-w-4xl h-full">
          <ChatInterface onNewChat={() => setRefreshKey(prev => prev + 1)} />
        </div>
      </div>
    </main>
  );
}
