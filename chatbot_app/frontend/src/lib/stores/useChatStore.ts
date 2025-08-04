import { create } from 'zustand';
import { Message } from '@/components/chat-interface';
import { ChatSession } from '@/lib/types';

interface ChatState {
  messages: Message[];
  sessionId: string | null;
  isLoading: boolean;
  isStreaming: boolean;
  currentStatus: string;
  statusVersion: number;
  chatSessions: ChatSession[];
  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;
  setLastMessageContent: (content: string) => void;
  appendLastMessageChunk: (chunk: string) => void;
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
  statusVersion: 0,
  chatSessions: [],
  setMessages: (messages: Message[]) => set({ messages }),
  addMessage: (message: Message) => set((state: ChatState) => ({ messages: [...state.messages, message] })),
  setLastMessageContent: (content: string) =>
    set((state: ChatState) => ({
      messages: state.messages.map((message, index) => {
        if (index === state.messages.length - 1) {
          return { ...message, content };
        }
        return message;
      }),
    })),
  appendLastMessageChunk: (chunk: string) =>
    set((state: ChatState) => ({
      messages: state.messages.map((message, index) => {
        if (index === state.messages.length - 1) {
          return {
            ...message,
            content: message.content + chunk,
          };
        }
        return message;
      }),
    })),
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
  setCurrentStatus: (currentStatus: string) => set((state) => ({ currentStatus, statusVersion: state.statusVersion + 1 })),
  setChatSessions: (sessions: ChatSession[]) => set({ chatSessions: sessions }),
  reset: () => set({ messages: [], sessionId: null, isLoading: false, isStreaming: false, currentStatus: "Thinking...", statusVersion: 0 }),
}));