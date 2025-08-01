import { useChatStore } from '../stores/useChatStore';
import { Message } from '@/components/chat-interface';

export function useChatApi() {
  const {
    addMessage,
    setSessionId,
    setIsLoading,
    setIsStreaming,
    setCurrentStatus,
    updateLastMessage,
    setLastMessageSourceDocuments,
    setMessages,
  } = useChatStore();

  const handleSendMessage = async (query: string, sessionId: string | null) => {
    if (query.trim()) {
      const userMessage: Message = { role: "user", content: query };
      addMessage(userMessage);
      setIsLoading(true);
      setIsStreaming(false);
      setCurrentStatus("Sending request...");

      const botMessagePlaceholder: Message = { role: "assistant", content: "", source_documents: [] };
      addMessage(botMessagePlaceholder);

      try {
        const response = await fetch("/api/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: query,
            stream: true,
            session_id: sessionId,
          }),
        });

        if (!response.ok || !response.body) {
          throw new Error("Network response was not ok");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const processStream = async () => {
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;

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

                if (event === 'user_message_saved') {
                  if (data.session_id && !sessionId) {
                    setSessionId(data.session_id);
                  }
                  // Logic to update user message with ID can be added here if needed
                } else if (event === 'status_update') {
                  setCurrentStatus(data.status);
                } else if (event === 'sources') {
                  setLastMessageSourceDocuments(data.sources);
                } else if (event === 'llm_response_chunk') {
                  if (!useChatStore.getState().isStreaming) {
                    setIsStreaming(true);
                    updateLastMessage('');
                  }
                  updateLastMessage(useChatStore.getState().messages[useChatStore.getState().messages.length - 1].content + data.token);
                } else if (event === 'error') {
                  updateLastMessage(data.message || "An unknown error occurred.");
                  setIsLoading(false);
                  setIsStreaming(false);
                  return;
                } else if (event === 'stream_end') {
                  setIsLoading(false);
                  setIsStreaming(false);
                  return;
                }
              } catch (e) {
                console.error("Error parsing SSE data:", e);
              }
            }
          }
        };

        await processStream();

      } catch (error) {
        const message = error instanceof Error ? error.message : "An unknown error occurred.";
        updateLastMessage(`Failed to fetch search results: ${message}`);
        setIsLoading(false);
        setIsStreaming(false);
      }
    }
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

  return { handleSendMessage, handleDeleteMessage };
}