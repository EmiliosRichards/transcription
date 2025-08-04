import { useChatStore } from '../stores/useChatStore';
import { Message } from '@/components/chat-interface';
import { useRef } from 'react';

export function useChatApi() {
  const {
    addMessage,
    setSessionId,
    setIsLoading,
    setIsStreaming,
    setCurrentStatus,
    setLastMessageContent,
    appendLastMessageChunk,
    setLastMessageSourceDocuments,
    setMessages,
    setChatSessions,
  } = useChatStore();

  const handleSendMessage = (query: string, sessionId: string | null) => {
    if (!query.trim()) return;

    const userMessage: Message = { id: Date.now(), role: "user", content: query };
    const botMessagePlaceholder: Message = { id: Date.now() + 1, role: "assistant", content: "" };
    addMessage(userMessage);
    addMessage(botMessagePlaceholder);

    setIsLoading(true);
    setIsStreaming(false);
    setCurrentStatus("Thinking...");

    const queryParams = new URLSearchParams({ query, stream: "true" });
    if (sessionId) queryParams.append("session_id", sessionId);

    const eventSource = new EventSource(`/api/search?${queryParams.toString()}`);

    const stopStreaming = () => {
      setIsLoading(false);
      setIsStreaming(false);
      eventSource.close();
    };

    eventSource.addEventListener('user_message_saved', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.session_id && !sessionId) setSessionId(data.session_id);
    });

    eventSource.addEventListener('status_update', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setCurrentStatus(data.status);
    });

    eventSource.addEventListener('sources', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setLastMessageSourceDocuments(data.sources);
    });

    eventSource.addEventListener('llm_response_chunk', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (!useChatStore.getState().isStreaming) {
        setIsStreaming(true);
        // This is the crucial two-step "priming" of the state from the working code
        setLastMessageContent(''); 
        appendLastMessageChunk(data.token);
      } else {
        appendLastMessageChunk(data.token);
      }
    });

    eventSource.addEventListener('error', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setLastMessageContent(data.message || "An error occurred.");
      stopStreaming();
    });

    eventSource.addEventListener('stream_end', () => {
      stopStreaming();
    });

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      setLastMessageContent("An error occurred while connecting to the server.");
      stopStreaming();
    };
  };

  const handleDeleteMessage = async (messageToDelete: Message, messages: Message[], sessionId: string | null) => {
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
        const isFirstMessage = messages[messageIndex].id === messages[0].id;

        if (isFirstMessage) {
            setMessages([]);
            setSessionId(null);
        } else {
            setMessages(messages.slice(0, messageIndex));
        }
      }
    } catch (error) {
      console.error("Error deleting message:", error);
    }
  };

  const handleFetchChatSessions = async () => {
    try {
      const response = await fetch("/api/chats");
      if (!response.ok) {
        throw new Error('Failed to fetch chat sessions');
      }
      const sessions = await response.json();
      setChatSessions(sessions);
    } catch (error) {
      console.error("Error fetching chat sessions:", error);
    }
  };

  return { handleSendMessage, handleDeleteMessage, handleFetchChatSessions };
}