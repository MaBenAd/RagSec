"use client";

import { create } from "zustand";
import { getMe as getMeApi, login as loginApi, logoutSession, register as registerApi, updateLanguage as updateLanguageApi } from "@/lib/api";
import { useChatStore } from "@/store/useChatStore";
import type { User } from "@/types";
import i18n from "@/lib/i18n";

interface AuthStore {
  user: User | null;
  token: string | null;
  hydrated: boolean;
  hydrate: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, classLabel: string | null, acceptedPrivacy: boolean) => Promise<void>;
  setLanguage: (lang: string) => Promise<void>;
  logout: () => Promise<void>;
  isAdmin: () => boolean;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  token: null,
  hydrated: false,
  hydrate: async () => {
    if (typeof window === "undefined") {
      set({ hydrated: true });
      return;
    }

    try {
      const user = await getMeApi();
      if (user?.language) {
        i18n.changeLanguage(user.language);
      }
      set({ token: "cookie", user, hydrated: true });
    } catch {
      set({ token: null, user: null, hydrated: true });
    }
  },
  login: async (email: string, password: string) => {
    const data = await loginApi(email, password);
    if (data.user.language) {
      i18n.changeLanguage(data.user.language);
    }
    
    set({ token: "cookie", user: data.user });
  },
  register: async (email: string, password: string, classLabel: string | null, acceptedPrivacy: boolean) => {
    const lang = i18n.language || "fr";
    const data = await registerApi(email, password, classLabel, lang, acceptedPrivacy);
    if (data.user.language) {
      i18n.changeLanguage(data.user.language);
    }
    
    set({ token: "cookie", user: data.user });
  },
  setLanguage: async (lang: string) => {
    const user = get().user;
    const token = get().token;
    if (user && token) {
      try {
        await updateLanguageApi(lang);
        const updatedUser = { ...user, language: lang };
        localStorage.setItem("user", JSON.stringify(updatedUser));
        set({ user: updatedUser });
      } catch (error) {
        console.error("Failed to sync language with backend:", error);
      }
    }
    i18n.changeLanguage(lang);
  },
  logout: async () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    try {
      await logoutSession();
    } catch {
      // Local logout still wins; the next authenticated request will fail cleanly.
    } finally {
      document.cookie = "token=; path=/; max-age=0; samesite=strict";
      document.cookie = "csrf_token=; path=/; max-age=0; samesite=strict";
      useChatStore.getState().resetSession();
      set({ token: null, user: null, hydrated: true });
    }
  },
  isAdmin: () => get().user?.role === "admin"
}));
