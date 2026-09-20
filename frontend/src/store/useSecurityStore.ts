"use client";
import { create } from "zustand";
import type { Message } from "@/types";
import { securityChat, securityLogout } from "@/lib/security-api";

interface State {
  messages: Message[];
  conversation: number | null;
  busy: boolean;
  controller: AbortController | null;
  send: (question: string, language: string, stream: boolean) => Promise<void>;
  reset: () => void;
  logout: () => void;
}

export const useSecurityStore = create<State>((set, get) => ({
  messages: [], conversation: null, busy: false, controller: null,
  reset: () => { get().controller?.abort(); set({ messages: [], conversation: null, busy: false, controller: null }); },
  logout: () => { securityLogout(); get().reset(); },
  send: async (question, language, stream) => {
    if (get().busy) return;
    const controller = new AbortController();
    const id = Date.now();
    const epoch = get().conversation;
    set(state => ({ busy: true, controller, messages: [...state.messages, {
      id, conversation_id: epoch ?? 0, role: "user", content: question, created_at: new Date().toISOString(),
    }] }));
    try {
      const outcome = await securityChat(question, language, stream, controller.signal, epoch);
      if (controller.signal.aborted) return;
      set(state => ({ conversation: outcome.conversation_id ?? state.conversation, messages: [...state.messages, {
        id: id + 1, conversation_id: outcome.conversation_id ?? 0, role: "assistant", content: outcome.answer,
        metadata: { security: outcome }, created_at: new Date().toISOString(),
      }] }));
    } finally { if (get().controller === controller) set({ busy: false, controller: null }); }
  },
}));
