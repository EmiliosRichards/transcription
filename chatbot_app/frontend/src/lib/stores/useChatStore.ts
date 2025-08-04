import { create } from 'zustand';
import { Message } from '@/components/chat-interface';
import { ChatSession } from '@/lib/types';

interface ChatState {
  messages: Message[];
  sessionId: string | null;
  isLoading: boolean;
  isStreaming: boolean;
  currentStatus: string;
  chatSessions: ChatSession[];
  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;
  updateLastMessage: (content: string) => void;
  setLastMessageSourceDocuments: (sourceDocuments: any[]) => void;
  setSessionId: (sessionId: string | null) => void;
  setIsLoading: (isLoading: boolean) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setCurrentStatus: (status: string) => void;
  setChatSessions: (sessions: ChatSession[]) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>()((set) => ({
  messages: [],
  sessionId: null,
  isLoading: false,
  isStreaming: false,
  currentStatus: "Thinking...",
  chatSessions: [],
  setMessages: (messages: Message[]) => set({ messages }),
  addMessage: (message: Message) => set((state: ChatState) => ({ messages: [...state.messages, message] })),
  updateLastMessage: (content: string) =>
    set((state: ChatState) => {
      const newMessages = [...state.messages];
      const lastMessage = newMessages[newMessages.length - 1];
      if (lastMessage) {
        newMessages[newMessages.length - 1] = { ...lastMessage, content };
      }
      return { messages: newMessages };
    }),
  setLastMessageSourceDocuments: (sourceDocuments: any[]) =>
    set((state: ChatState) => {
      const newMessages = [...state.messages];
      const lastMessage = newMessages[newMessages.length - 1];
      if (lastMessage) {
        newMessages[newMessages.length - 1] = { ...lastMessage, source_documents: sourceDocuments };
      }
      return { messages: newMessages };
    }),
  setSessionId: (sessionId: string | null) => set({ sessionId }),
  setIsLoading: (isLoading: boolean) => set({ isLoading }),
  setIsStreaming: (isStreaming: boolean) => set({ isStreaming }),
  setCurrentStatus: (currentStatus: string) => set({ currentStatus }),
  setChatSessions: (sessions: ChatSession[]) => set({ chatSessions: sessions }),
  reset: () => set({ messages: [], sessionId: null, isLoading: false, isStreaming: false, currentStatus: "Thinking..." }),
}));