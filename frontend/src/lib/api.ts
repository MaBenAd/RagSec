import axios from "axios";
import type { ChatResponse, ClassChangeRequest, Conversation, EdtClassInfo, LoginResponse, Message, PublishedTimetable, QaPair, StatsResponse, Timetable, User, UserActivity } from "@/types";

export interface FaqPreviewResponse {
  filename: string;
  file_type: string;
  snippet_count: number;
  truncated: boolean;
  text: string;
}

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000",
  withCredentials: true
});

function getClientLanguage() {
  if (typeof window === "undefined") return "fr";
  const fromI18n = localStorage.getItem("i18nextLng")?.slice(0, 2);
  if (fromI18n && ["fr", "en", "ar"].includes(fromI18n)) return fromI18n;
  try {
    const user = JSON.parse(localStorage.getItem("user") || "null") as User | null;
    if (user?.language && ["fr", "en", "ar"].includes(user.language)) return user.language;
  } catch {
    // Ignore malformed local storage and fall back below.
  }
  const browserLang = navigator.language?.slice(0, 2);
  return browserLang && ["fr", "en", "ar"].includes(browserLang) ? browserLang : "fr";
}

function setBrowserToken(token: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem("token", token);
  document.cookie = `token=${encodeURIComponent(token)}; path=/; max-age=${15 * 60}; samesite=strict`;
}

function clearBrowserSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  document.cookie = "token=; path=/; max-age=0; samesite=strict";
  document.cookie = "csrf_token=; path=/; max-age=0; samesite=strict";
}

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    config.headers["Accept-Language"] = getClientLanguage();
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const requestUrl = String(originalRequest?.url ?? "");
    const isAuthProbe =
      requestUrl.includes("/api/v1/auth/me") ||
      requestUrl.includes("/api/v1/auth/refresh") ||
      requestUrl.includes("/api/v1/auth/login") ||
      requestUrl.includes("/api/v1/auth/register") ||
      requestUrl.includes("/api/v1/auth/logout");

    if (error.response?.status === 401 && !originalRequest?._retry && !isAuthProbe) {
      originalRequest._retry = true;
      try {
        const { access_token } = await refreshToken();
        if (typeof window !== "undefined") {
          setBrowserToken(access_token);
        }
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        clearBrowserSession();
        if (typeof window !== "undefined" && window.location.pathname !== "/login") {
          window.location.replace("/login");
        }
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/api/v1/auth/login", { email, password });
  if (typeof window !== "undefined") {
    setBrowserToken(data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
  }
  return data;
}

export async function logout(): Promise<{ success: boolean }> {
  const { data } = await api.post<{ success: boolean }>("/api/v1/auth/logout");
  return data;
}

export const logoutSession = logout;

export async function refreshToken(): Promise<LoginResponse> {
  // Use a separate axios instance or a direct call to avoid interceptor loops if needed,
  // but here we just call the endpoint.
  const { data } = await api.post<LoginResponse>("/api/v1/auth/refresh");
  return data;
}

export async function getMe(): Promise<User> {
  const { data } = await api.get<User>("/api/v1/auth/me");
  if (typeof window !== "undefined") {
    localStorage.setItem("user", JSON.stringify(data));
  }
  return data;
}

export async function register(
  email: string,
  password: string,
  class_label: string | null,
  language: string = "fr",
  accepted_privacy: boolean = false,
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/api/v1/auth/register", {
    email,
    password,
    class_label,
    language,
    accepted_privacy,
  });
  if (typeof window !== "undefined") {
    setBrowserToken(data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
  }
  return data;
}

export async function updateLanguage(language: string): Promise<{ success: boolean }> {
  const { data } = await api.post<{ success: boolean }>("/api/v1/auth/me/language", { language });
  return data;
}

export async function getMeActivity(): Promise<{ day: string; count: number }[]> {
  const { data } = await api.get<{ activity: { day: string; count: number }[] }>("/api/v1/auth/me/activity");
  return data.activity;
}

export async function deleteMeAccount(): Promise<{ success: boolean }> {
  const { data } = await api.delete<{ success: boolean }>("/api/v1/auth/me");
  return data;
}

export async function exportMyData(): Promise<any> {
  const { data } = await api.get("/api/v1/auth/me/export");
  return data;
}

export async function getMeTimetable(): Promise<Timetable | null> {
  const { data } = await api.get<{ timetable: Timetable | null }>("/api/v1/auth/me/timetable");
  return data.timetable;
}

export async function sendMessage(question: string, class_label: string | null, conversation_id?: number | null): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>("/api/v1/chat", {
    question,
    class_label,
    conversation_id: conversation_id ?? null
  });
  return data;
}

export async function* streamMessage(question: string, class_label: string | null, conversation_id?: number | null, signal?: AbortSignal) {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  
  const response = await fetch(`${baseUrl}/api/v1/chat/stream`, {
    method: "POST",
    signal,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "Accept-Language": getClientLanguage(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question,
      class_label,
      conversation_id: conversation_id ?? null,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Streaming error" }));
    throw new Error(err.detail || "Streaming error");
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) return;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split("\n\n");

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6);
        if (data === "[DONE]") return;
        
        if (data.startsWith("__metadata__:")) {
          try {
            const meta = JSON.parse(data.replace("__metadata__:", ""));
            yield { type: "metadata", ...meta };
          } catch (e) {
            console.error("Error parsing metadata", e);
          }
        } else {
          yield { type: "text", content: data };
        }
      }
    }
  }
}

export async function giveFeedback(messageId: number, feedback: number): Promise<{ success: boolean }> {
  const { data } = await api.post<{ success: boolean }>(`/api/v1/chat/feedback/${messageId}`, { feedback });
  return data;
}

export async function getConversations(): Promise<Conversation[]> {
  const { data } = await api.get<{ conversations: Conversation[] }>("/api/v1/conversations");
  return data.conversations;
}

export async function getMessages(convId: number): Promise<Message[]> {
  const { data } = await api.get<{ messages: Message[] }>(`/api/v1/conversations/${convId}/messages`);
  return data.messages;
}

export async function deleteConversation(convId: number): Promise<{ success: boolean }> {
  const { data } = await api.delete<{ success: boolean }>(`/api/v1/conversations/${convId}`);
  return data;
}

export async function getStats(): Promise<StatsResponse> {
  const { data } = await api.get<StatsResponse>("/api/v1/admin/stats");
  return data;
}

export async function uploadFaq(file: File, rebuild = true): Promise<{ success: boolean; message: string; filename: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post(`/api/v1/admin/upload/faq?rebuild=${String(rebuild)}`, formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

export async function getFaqFiles(): Promise<FaqFileLike[]> {
  const { data } = await api.get<{ files: FaqFileLike[] }>("/api/v1/admin/faq/files");
  return data.files;
}

export async function deleteFaqFile(filename: string): Promise<{ success: boolean }> {
  const { data } = await api.delete<{ success: boolean }>(`/api/v1/admin/faq/files/${encodeURIComponent(filename)}`);
  return data;
}

export async function rebuildVectorstore(): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post<{ success: boolean; message: string }>("/api/v1/admin/faq/rebuild");
  return data;
}

export async function flushCache(): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post<{ success: boolean; message: string }>("/api/v1/admin/cache/flush");
  return data;
}

export async function cleanupOldData(days: number = 180): Promise<{ success: boolean; deleted_count: number; message: string }> {
  const { data } = await api.post<{ success: boolean; deleted_count: number; message: string }>(`/api/v1/admin/data/cleanup?days=${days}`);
  return data;
}

export async function deleteUser(userId: number): Promise<{ success: boolean }> {
  const { data } = await api.delete<{ success: boolean }>(`/api/v1/admin/users/${userId}`);
  return data;
}

export async function getPublishedTimetables(): Promise<PublishedTimetable[]> {
  const { data } = await api.get<{ timetables: PublishedTimetable[] }>("/api/v1/admin/edt/published");
  return data.timetables;
}

export async function getPublishedTimetableDetails(timetableId: number): Promise<Timetable> {
  const { data } = await api.get<{ timetable: Timetable }>(`/api/v1/admin/edt/published/${timetableId}`);
  return data.timetable;
}

export async function deletePublishedTimetable(timetableId: number): Promise<{ success: boolean }> {
  const { data } = await api.delete<{ success: boolean }>(`/api/v1/admin/edt/published/${timetableId}`);
  return data;
}

export async function previewFaqFile(filename: string): Promise<FaqPreviewResponse> {
  const { data } = await api.get<FaqPreviewResponse>(`/api/v1/admin/faq/files/${encodeURIComponent(filename)}/preview`);
  return data;
}

export async function getFaqFileBlob(filename: string): Promise<Blob> {
  const response = await api.get<Blob>(`/api/v1/admin/faq/files/${encodeURIComponent(filename)}/download`, {
    responseType: "blob"
  });

  return new Blob([response.data], {
    type: typeof response.headers["content-type"] === "string" 
      ? response.headers["content-type"] 
      : "application/octet-stream"
  });
}

export async function downloadFaqFile(filename: string): Promise<void> {
  const blob = await getFaqFileBlob(filename);
  const blobUrl = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(blobUrl);
}

export async function getQaPairs(): Promise<QaPair[]> {
  const { data } = await api.get<{
    qa_pairs: Array<{
      question: string;
      response?: string;
      answer?: string;
      user_email?: string;
      email?: string;
      created_at: string;
    }>;
  }>("/api/v1/admin/conversations");
  return data.qa_pairs.map((row) => ({
    question: row.question ?? "",
    answer: row.answer ?? row.response ?? "",
    email: row.email ?? row.user_email ?? "-",
    created_at: row.created_at,
  }));
}

export async function getUsers(query = ""): Promise<UserActivity[]> {
  const qs = query ? `?query=${encodeURIComponent(query)}` : "";
  const { data } = await api.get<{ users: UserActivity[] }>(`/api/v1/admin/users${qs}`);
  return data.users;
}

export async function getEdtClasses(): Promise<EdtClassInfo[]> {
  const { data } = await api.get<{ classes: EdtClassInfo[] }>("/api/v1/edt/classes");
  return data.classes;
}

export async function requestClassChange(requestedClassLabel: string, reason?: string): Promise<ClassChangeRequest> {
  const { data } = await api.post<{ success: boolean; request: ClassChangeRequest }>("/api/v1/class-change-requests", {
    requested_class_label: requestedClassLabel,
    reason: reason ?? null
  });
  return data.request;
}

export async function getMyClassChangeRequests(): Promise<ClassChangeRequest[]> {
  const { data } = await api.get<{ requests: ClassChangeRequest[] }>("/api/v1/class-change-requests/me");
  return data.requests;
}

export async function getAdminClassChangeRequests(status: "pending" | "approved" | "rejected" | "all" = "pending"): Promise<ClassChangeRequest[]> {
  const { data } = await api.get<{ requests: ClassChangeRequest[] }>(`/api/v1/admin/class-change-requests?request_status=${status}`);
  return data.requests;
}

export async function decideClassChangeRequest(requestId: number, decision: "approve" | "reject", note?: string): Promise<ClassChangeRequest> {
  const { data } = await api.post<{ success: boolean; request: ClassChangeRequest }>(`/api/v1/admin/class-change-requests/${requestId}/decision`, {
    decision,
    note: note ?? null
  });
  return data.request;
}

interface FaqFileLike {
  name: string;
  size_kb: number;
  updated_at: string;
}

export async function setQuestionReviewStatus(question: string, status: "pending" | "treated", note?: string): Promise<{ success: boolean }> {
  const { data } = await api.post("/api/v1/admin/faq/review", {
    question,
    status,
    note: note ?? null
  });
  return data;
}

export async function publishTimetable(payload: any): Promise<{ success: boolean; timetable_id: number }> {
  const { data } = await api.post("/api/v1/admin/edt/publish", payload);
  return data;
}
