"use client";

import { create } from "zustand";
import { deleteConversation, getConversations, getMessages, streamMessage, giveFeedback } from "@/lib/api";
import type { Conversation, Message } from "@/types";
import { toast } from "sonner";

interface ChatStore {
  conversations: Conversation[];
  currentConvId: number | null;
  messages: Message[];
  selectedClass: string | null;
  isLoading: boolean;
  abortController: AbortController | null;
  loadConversations: () => Promise<void>;
  selectConversation: (id: number) => Promise<void>;
  send: (question: string) => Promise<void>;
  cancelGeneration: () => void;
  newConversation: () => void;
  removeConversation: (id: number) => Promise<void>;
  setClass: (value: string | null) => void;
  resetSession: () => void;
  giveFeedback: (messageId: number, feedback: number) => Promise<void>;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  conversations: [],
  currentConvId: null,
  messages: [],
  selectedClass: null,
  isLoading: false,
  abortController: null,
  loadConversations: async () => {
    const conversations = await getConversations();
    set({ conversations });
  },
  selectConversation: async (id: number) => {
    const messages = await getMessages(id);
    set({ currentConvId: id, messages });
  },
  send: async (question: string) => {
    if (get().isLoading) return;

    const abortController = new AbortController();
    const timeoutId = window.setTimeout(() => abortController.abort(), 90000);
    set({ isLoading: true, abortController });

    const userMessageId = Date.now();
    const userMessage: Message = {
      id: userMessageId,
      conversation_id: get().currentConvId ?? 0,
      role: "user",
      content: question,
      created_at: new Date().toISOString()
    };
    
    const assistantMessageId = userMessageId + 1;
    const assistantMessage: Message = {
      id: assistantMessageId,
      conversation_id: get().currentConvId ?? 0,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString()
    };

    set((state) => ({ messages: [...state.messages, userMessage, assistantMessage] }));

    try {
      let fullContent = "";
      const stream = streamMessage(question, get().selectedClass, get().currentConvId, abortController.signal);
      
      for await (const chunk of stream) {
        if (chunk.type === "metadata") {
          set((state) => ({
            messages: state.messages.map((m) => 
              m.id === assistantMessageId ? { 
                ...m, 
                source_file: chunk.source_files,
                metadata: { ...m.metadata, ...chunk } 
              } : m
            )
          }));
        } else {
          fullContent += chunk.content;
          set((state) => ({
            messages: state.messages.map((m) => 
              m.id === assistantMessageId ? { ...m, content: fullContent } : m
            )
          }));
        }
      }

      await get().loadConversations();
      // If it was a new conversation, we need to find the ID from the updated conversations list
      if (!get().currentConvId) {
        const conversations = await getConversations();
        const latest = conversations[0];
        if (latest) {
          set({ currentConvId: latest.id });
        }
      }
      
      // Reload messages to get the correct database IDs and metadata
      if (get().currentConvId) {
        const updatedMessages = await getMessages(get().currentConvId!);
        set({ messages: updatedMessages });
      }
    } catch (error) {
      console.error("Streaming error:", error);
      const wasAborted = abortController.signal.aborted;
      set((state) => ({
        messages: state.messages.map((m) =>
          m.id === assistantMessageId
            ? {
                ...m,
                content: m.content || (wasAborted ? "Generation interrompue." : "Erreur de communication avec l'IA."),
              }
            : m
        ),
      }));
      toast.error(wasAborted ? "Generation interrompue" : "Erreur de communication avec l'IA");
    } finally {
      window.clearTimeout(timeoutId);
      set({ isLoading: false, abortController: null });
    }
  },
  cancelGeneration: () => {
    get().abortController?.abort();
  },
  giveFeedback: async (messageId: number, feedback: number) => {
    try {
      await giveFeedback(messageId, feedback);
      set((state) => ({
        messages: state.messages.map((m) => 
          m.id === messageId ? { ...m, feedback } : m
        )
      }));
    } catch (error) {
      console.error("Feedback error:", error);
      toast.error("Erreur lors de l'envoi du feedback");
    }
  },
  newConversation: () => {
    set({ currentConvId: null, messages: [] });
  },
  removeConversation: async (id: number) => {
    await deleteConversation(id);
    set((state) => ({
      conversations: state.conversations.filter((conv) => conv.id !== id),
      currentConvId: state.currentConvId === id ? null : state.currentConvId,
      messages: state.currentConvId === id ? [] : state.messages,
    }));
  },
  setClass: (value: string | null) => {
    set({ selectedClass: value });
  },
  resetSession: () => {
    set({
      conversations: [],
      currentConvId: null,
      messages: [],
      selectedClass: null,
      isLoading: false,
      abortController: null,
    });
  }
}));
