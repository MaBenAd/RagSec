"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuthStore } from "@/store/useAuthStore";
import { useChatStore } from "@/store/useChatStore";
import { useTheme } from "@/components/providers/ThemeProvider";
import { useTranslation } from "react-i18next";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { ChatInput } from "@/components/chat/ChatInput";
import { TypingDots } from "@/components/chat/TypingDots";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import Modal from "@/components/Modal";
import PrivacyPolicies from "@/components/PrivacyPolicies";
import { getMeTimetable } from "@/lib/api";
import { formatClassLabel } from "@/lib/timetable";
import type { Timetable } from "@/types";
import {
  Plus,
  MessageSquare,
 
  Trash2, 
  LogOut, 
  ChevronRight, 
  Menu, 
  X, 
  Sun, 
  Moon,
  GraduationCap,
  Sparkles,
  Settings,
  Calendar,
  Check,
  PanelLeftClose,
  PanelLeftOpen
} from "lucide-react";

const EXAMPLES = [
  "Où est la scolarité ?",
  "Avez-vous une buvette ?",
  "Où consulter le calendrier des examens ?",
  "Quel est l'emploi du temps de TDI S4 ?",
  "Comment obtenir une attestation ?",
];

const WEEKDAY_CONFIG: Array<{ label: string; jsDay: number; ttDayIndex: number | null }> = [
  { label: "Lundi", jsDay: 1, ttDayIndex: 0 },
  { label: "Mardi", jsDay: 2, ttDayIndex: 1 },
  { label: "Mercredi", jsDay: 3, ttDayIndex: 2 },
  { label: "Jeudi", jsDay: 4, ttDayIndex: 3 },
  { label: "Vendredi", jsDay: 5, ttDayIndex: 4 },
  { label: "Samedi", jsDay: 6, ttDayIndex: 5 },
  { label: "Dimanche", jsDay: 0, ttDayIndex: null },
];

interface StudyPlanItem {
  id: string;
  dateLabel: string;
  sessionWindow: string;
  durationHours: number;
  focus: string;
  note?: string;
  isExamDay?: boolean;
}

function formatConversationDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Récente";
  return date.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
}

function extractFirstNameFromEmail(email?: string | null): string {
  if (!email) return "Etudiant";
  const local = email.split("@")[0] || "";
  const firstChunk = local.split(".")[0] || local;
  const cleaned = firstChunk.replace(/[^a-zA-ZÀ-ÿ0-9\-_]/g, " ").trim();
  if (!cleaned) return "Etudiant";
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function parseClockToMinutes(value?: string | null): number | null {
  if (!value) return null;
  const match = String(value).match(/(\d{1,2}):(\d{2})/);
  if (!match) return null;
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

function minutesToClock(value: number): string {
  const minutesInDay = 24 * 60;
  const normalized = ((Math.round(value) % minutesInDay) + minutesInDay) % minutesInDay;
  const h = Math.floor(normalized / 60);
  const m = normalized % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function weekdayLabelFromDate(date: Date): string {
  const config = WEEKDAY_CONFIG.find((item) => item.jsDay === date.getDay());
  return config?.label ?? "Jour";
}

function buildStudyPlan(
  examName: string,
  examDateValue: string,
  dailyHours: number,
  unavailableDays: Set<string>,
  timetable: Timetable | null,
): StudyPlanItem[] {
  const examDate = new Date(`${examDateValue}T00:00:00`);
  if (Number.isNaN(examDate.getTime())) return [];

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (examDate <= today) return [];

  const busyByDay = new Map<number, { totalHours: number; latestEnd: number | null }>();
  for (const slot of timetable?.slots ?? []) {
    if (typeof slot.day_of_week !== "number") continue;
    const start = parseClockToMinutes(slot.start_time);
    const end = parseClockToMinutes(slot.end_time);
    if (start === null || end === null || end <= start) continue;

    const current = busyByDay.get(slot.day_of_week) ?? { totalHours: 0, latestEnd: null };
    current.totalHours += (end - start) / 60;
    current.latestEnd = current.latestEnd === null ? end : Math.max(current.latestEnd, end);
    busyByDay.set(slot.day_of_week, current);
  }

  const items: StudyPlanItem[] = [];
  let cursor = new Date(today);
  cursor.setDate(cursor.getDate() + 1);

  while (cursor < examDate) {
    const dayLabel = weekdayLabelFromDate(cursor);
    if (unavailableDays.has(dayLabel)) {
      cursor.setDate(cursor.getDate() + 1);
      continue;
    }

    const dayConfig = WEEKDAY_CONFIG.find((item) => item.jsDay === cursor.getDay());
    const ttDayIndex = dayConfig?.ttDayIndex;
    const busy = ttDayIndex !== null && ttDayIndex !== undefined
      ? busyByDay.get(ttDayIndex) ?? { totalHours: 0, latestEnd: null }
      : { totalHours: 0, latestEnd: null };

    const reduction = busy.totalHours >= 6 ? 1 : busy.totalHours >= 4 ? 0.75 : busy.totalHours >= 2 ? 0.5 : 0;
    const sessionHours = Math.max(0.5, Math.round((dailyHours - reduction) * 2) / 2);
    const startMinutes = busy.latestEnd !== null ? Math.max(busy.latestEnd + 30, 18 * 60) : 18 * 60;
    const endMinutes = startMinutes + sessionHours * 60;

    items.push({
      id: `${cursor.toISOString()}-${items.length}`,
      dateLabel: cursor.toLocaleDateString("fr-FR", { weekday: "long", day: "2-digit", month: "2-digit" }),
      sessionWindow: `${minutesToClock(startMinutes)} - ${minutesToClock(endMinutes)}`,
      durationHours: sessionHours,
      focus: items.length < 3
        ? `Apprentissage actif de ${examName}`
        : items.length < 6
          ? `Exercices et annales: ${examName}`
          : `Revision finale: ${examName}`,
      note: busy.totalHours >= 5 ? "Jour charge: session plus compacte" : undefined,
    });

    cursor.setDate(cursor.getDate() + 1);
  }

  const examDayLabel = weekdayLabelFromDate(examDate);
  if (!unavailableDays.has(examDayLabel)) {
    items.push({
      id: `exam-${examDate.toISOString()}`,
      dateLabel: `${examDate.toLocaleDateString("fr-FR", { weekday: "long", day: "2-digit", month: "2-digit" })} (Examen)`,
      sessionWindow: "08:00 - 08:45",
      durationHours: 0.75,
      focus: `Relecture legere et check final: ${examName}`,
      note: "Pas de surcharge le jour J",
      isExamDay: true,
    });
  }

  return items;
}

export default function ChatPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const auth = useAuthStore();
  const chat = useChatStore();
  const { theme, toggleTheme } = useTheme();
  
  const listRef = useRef<HTMLDivElement>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isPolicyModalOpen, setIsPolicyModalOpen] = useState(false);
  const [isPlannerOpen, setIsPlannerOpen] = useState(false);
  const [plannerLoading, setPlannerLoading] = useState(false);
  const [plannerTimetable, setPlannerTimetable] = useState<Timetable | null>(null);
  const [plannerExamName, setPlannerExamName] = useState("");
  const [plannerExamDate, setPlannerExamDate] = useState("");
  const [plannerDailyHours, setPlannerDailyHours] = useState("2");
  const [plannerUnavailableDays, setPlannerUnavailableDays] = useState<string[]>(["Samedi"]);
  const [plannerError, setPlannerError] = useState<string | null>(null);
  const [plannerResult, setPlannerResult] = useState<StudyPlanItem[]>([]);

  useEffect(() => {
    useAuthStore.getState().hydrate();
  }, []);

  useEffect(() => {
    if (auth.hydrated && !auth.token) {
      router.replace("/login");
    }
  }, [auth.hydrated, auth.token, router]);

  useEffect(() => {
    if (!auth.hydrated || !auth.token || !auth.user) return;
    const chatState = useChatStore.getState();
    chatState.resetSession();
    const classFromProfile = auth.user.class_label || null;
    chatState.setClass(classFromProfile);
    chatState.loadConversations().catch(() => toast.error("Impossible de charger les conversations"));
  }, [auth.hydrated, auth.token, auth.user]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [chat.messages, chat.isLoading]);

  useEffect(() => {
    if (!isPlannerOpen || plannerLoading || plannerTimetable !== null) return;
    setPlannerLoading(true);
    getMeTimetable()
      .then((tt) => setPlannerTimetable(tt))
      .catch(() => setPlannerTimetable(null))
      .finally(() => setPlannerLoading(false));
  }, [isPlannerOpen, plannerLoading, plannerTimetable]);

  const activeConversation = chat.conversations.find((c) => c.id === chat.currentConvId) ?? null;
  const firstName = extractFirstNameFromEmail(auth.user?.email);
  const currentContext = auth.user?.class_label ? formatClassLabel(auth.user.class_label) : null;

  const handleSend = async (value: string) => {
    try {
      await chat.send(value);
    } catch {
      toast.error("Erreur lors de l'envoi du message");
    }
  };

  const handleDeleteConversation = async (id: number) => {
    try {
      await chat.removeConversation(id);
      toast.success("Discussion supprimée");
    } catch {
      toast.error("Impossible de supprimer la discussion");
    }
  };

  const logout = async () => {
    await auth.logout();
    router.replace("/login");
  };

  const togglePlannerUnavailableDay = (dayLabel: string) => {
    setPlannerUnavailableDays((prev) =>
      prev.includes(dayLabel) ? prev.filter((day) => day !== dayLabel) : [...prev, dayLabel]
    );
  };

  const handleGeneratePlan = () => {
    setPlannerError(null);
    setPlannerResult([]);

    const examName = plannerExamName.trim();
    const examDate = plannerExamDate.trim();
    const dailyHours = Number(plannerDailyHours);

    if (!examName) {
      setPlannerError("Ajoute le nom du module ou de l'examen.");
      return;
    }
    if (!examDate) {
      setPlannerError("Choisis la date de l'examen.");
      return;
    }
    if (!Number.isFinite(dailyHours) || dailyHours <= 0) {
      setPlannerError("Le temps quotidien doit etre superieur a 0.");
      return;
    }

    const result = buildStudyPlan(
      examName,
      examDate,
      dailyHours,
      new Set(plannerUnavailableDays),
      plannerTimetable,
    );

    if (result.length === 0) {
      setPlannerError("Impossible de generer un planning avec ces parametres. Verifie la date et les contraintes.");
      return;
    }

    setPlannerResult(result);
  };

  return (
    <main className="flex h-screen bg-background overflow-hidden font-inter">
      {/* Mobile Overlay */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-ensa-navy/20 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 bg-card border-r border-border z-50 transform transition-all duration-300
        ${isSidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        ${isCollapsed ? "lg:w-[68px]" : "lg:w-[260px]"}
        w-[260px] flex flex-col shadow-xl lg:shadow-none
      `}>
        <div className={`p-4 bg-ensa-navy relative overflow-hidden transition-all duration-300 ${isCollapsed ? "h-20 px-3" : ""}`}>
          <div className="absolute top-0 left-0 w-full h-full bg-[linear-gradient(135deg,_rgba(255,255,255,0.05)_0%,_transparent_100%)]" />
          <div className={`relative z-10 flex items-center ${isCollapsed ? "justify-center" : "justify-between"}`}>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 bg-white rounded-lg flex items-center justify-center shadow-lg shrink-0">
                <GraduationCap size={18} className="text-ensa-navy" />
              </div>
              {!isCollapsed && (
                <div className="leading-tight animate-in fade-in duration-500">
                  <h2 className="font-poppins font-bold text-white text-base tracking-tight">Chatbot ENSA</h2>
                  <p className="text-blue-200/60 text-[9px] uppercase font-bold tracking-widest">Béni Mellal</p>
                </div>
              )}
            </div>
            {!isCollapsed && (
              <button onClick={() => setIsSidebarOpen(false)} className="lg:hidden p-1.5 text-white/70 hover:text-white" aria-label="Close sidebar">
                <X size={18} />
              </button>
            )}
          </div>
          
          {/* Desktop Collapse Toggle */}
          <button 
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={`hidden lg:flex absolute bottom-1.5 right-1.5 p-1 rounded-md bg-white/10 text-white/50 hover:bg-white/20 hover:text-white transition-all focus-visible:ring-2 focus-visible:ring-white`}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? <PanelLeftOpen size={12} /> : <PanelLeftClose size={12} />}
          </button>
        </div>

        <div className={`p-3 border-b border-border bg-muted/30 transition-all ${isCollapsed ? "px-1.5" : ""}`}>
          <button
            onClick={() => {
              chat.newConversation();
              setIsSidebarOpen(false);
            }}
            className={`w-full flex items-center justify-center gap-2 bg-ensa-blue text-white rounded-xl font-poppins font-semibold text-xs transition-all shadow-md hover:bg-ensa-navy hover:shadow-ensa-blue/20 focus-visible:ring-2 focus-visible:ring-ensa-blue ${isCollapsed ? "h-10 w-10 mx-auto p-0" : "py-2.5 px-3"}`}
            title={t("chat.new_discussion")}
            aria-label={t("chat.new_discussion")}
          >
            <Plus size={16} />
            {!isCollapsed && <span className="animate-in fade-in duration-300">{t("chat.new_discussion")}</span>}
          </button>
        </div>

        <div className={`flex-1 overflow-y-auto p-3 space-y-1 custom-scrollbar bg-card ${isCollapsed ? "px-1.5" : ""}`}>
          {!isCollapsed && <p className="px-2 mb-2 text-[9px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 animate-in fade-in">{t("chat.discussion_history")}</p>}
          {chat.conversations.map((c) => (
            <div
              key={c.id}
              className={`
                group relative flex items-center gap-2.5 rounded-xl cursor-pointer transition-all border
                ${isCollapsed ? "p-2.5 justify-center" : "p-3"}
                ${c.id === chat.currentConvId 
                  ? "bg-ensa-blue/5 border-ensa-blue/20 text-ensa-navy dark:text-blue-100 shadow-sm" 
                  : "bg-transparent text-foreground border-transparent hover:bg-muted/50"}
              `}
              onClick={() => {
                chat.selectConversation(c.id);
                setIsSidebarOpen(false);
              }}
              title={isCollapsed ? c.title : undefined}
            >
              <MessageSquare size={16} className={`shrink-0 ${c.id === chat.currentConvId ? "text-ensa-blue" : "text-muted-foreground/60"}`} />
              {!isCollapsed && (
                <div className="flex-1 min-w-0 animate-in fade-in slide-in-from-left-2 duration-300">
                  <p className={`text-xs font-semibold truncate ${c.id === chat.currentConvId ? "text-ensa-navy dark:text-blue-100" : "text-foreground/80"}`}>{c.title}</p>
                  <p className="text-[9px] font-bold text-muted-foreground/50 uppercase tracking-tighter mt-0.5">
                    {formatConversationDate(c.created_at)}
                  </p>
                </div>
              )}
              {!isCollapsed && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteConversation(c.id);
                  }}
                  className={`opacity-0 group-hover:opacity-100 p-1 hover:bg-destructive/10 hover:text-destructive rounded-md transition-all
                    ${c.id === chat.currentConvId ? "text-ensa-blue" : "text-muted-foreground"}`}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          ))}
          {chat.conversations.length === 0 && (
            <div className={`p-8 text-center border-2 border-dashed border-border rounded-2xl opacity-40 ${isCollapsed ? "p-4" : ""}`}>
              <MessageSquare size={isCollapsed ? 20 : 32} className="mx-auto mb-3 opacity-20" />
              {!isCollapsed && <p className="text-xs font-medium">Aucune discussion</p>}
            </div>
          )}
        </div>

        <div className={`p-3 border-t border-border bg-muted/20 space-y-3 ${isCollapsed ? "px-1.5" : ""}`}>
          <div className={`p-3 rounded-xl bg-card border border-border shadow-sm ${isCollapsed ? "p-1.5" : ""}`}>
            <div className={`flex items-center gap-2.5 ${isCollapsed ? "justify-center mb-0 pb-0 border-none" : "mb-3 pb-3 border-b border-border/50"}`}>
              <div 
                onClick={() => router.push("/profile")}
                className="w-8 h-8 rounded-lg bg-ensa-navy text-white flex items-center justify-center font-bold text-xs shadow-md shrink-0 cursor-pointer hover:scale-110 transition-transform" 
                title={isCollapsed ? firstName : t("profile.title", { defaultValue: "Mon Profil" })}
              >
                {firstName[0]?.toUpperCase() || "E"}
              </div>
              {!isCollapsed && (
                <div 
                  className="flex-1 min-w-0 animate-in fade-in duration-300 cursor-pointer hover:opacity-70 transition-opacity"
                  onClick={() => router.push("/profile")}
                >
                  <p className="text-[11px] font-bold text-ensa-navy dark:text-blue-100 truncate">{firstName}</p>
                  <div className="flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-ensa-emerald animate-pulse" />
                    <p className="text-[9px] font-bold uppercase text-ensa-emerald tracking-widest">{auth.user?.role}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {!isCollapsed && (
            <button
              onClick={() => setIsPolicyModalOpen(true)}
              className="w-full flex items-center justify-center gap-2 border border-border py-2 rounded-xl text-muted-foreground hover:bg-muted transition-all font-poppins font-bold uppercase text-[9px] tracking-widest mb-1"
            >
              <Sparkles size={14} className="text-ensa-blue" />
              {t("auth.policies")}
            </button>
          )}

          <div className={`flex ${isCollapsed ? "flex-col" : "flex-row"} gap-2`}>
            <button
              onClick={toggleTheme}
              className="flex-1 flex items-center justify-center gap-2 border border-border py-2 rounded-xl hover:bg-muted transition-all"
              title="Changer de thème"
            >
              {theme === "dark" ? <Sun size={16} className="text-ensa-orange" /> : <Moon size={16} className="text-ensa-navy" />}
            </button>

            <LanguageSwitcher isCollapsed={isCollapsed} />

            <button
              onClick={logout}
              aria-label="Déconnexion"
              data-testid="logout-button"
              className="flex-1 flex items-center justify-center gap-2 border border-border py-2 rounded-xl text-destructive hover:bg-destructive/5 transition-all font-poppins font-bold uppercase text-[9px] tracking-widest"
              title="Déconnexion"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Chat Area */}
      <section className="flex-1 flex flex-col min-w-0 relative bg-background">
        <header className="h-16 border-b border-border bg-card/80 backdrop-blur-md px-4 flex items-center justify-between sticky top-0 z-30">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => setIsSidebarOpen(true)} className="lg:hidden p-2 border border-border rounded-lg bg-card">
              <Menu size={18} className="text-ensa-navy dark:text-white" />
            </button>
            <div className="min-w-0">
              <h1 className="font-poppins font-bold text-xs uppercase tracking-wider text-ensa-navy dark:text-blue-100 truncate">
                {activeConversation?.title ?? t("chat.new_assistant", { defaultValue: "Nouvel Assistant" })}
              </h1>
              <div className="flex items-center gap-1.5">
                <div className={`w-1.5 h-1.5 rounded-full ${chat.isLoading ? "bg-ensa-orange animate-pulse" : "bg-ensa-emerald"}`} />
                <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground/70">
                  {chat.isLoading ? t("common.generating", { defaultValue: "Génération..." }) : t("common.ia_operational", { defaultValue: "IA Opérationnelle" })}
                </span>
                {currentContext && (
                  <span className="hidden sm:inline text-[9px] font-bold text-muted-foreground/60">
                    · {t("chat.current_context", { defaultValue: "Contexte actuel" })}: {currentContext}
                  </span>
                )}
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsPlannerOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 border border-ensa-blue/20 bg-ensa-blue/5 rounded-lg text-[9px] font-bold uppercase tracking-widest text-ensa-blue hover:bg-ensa-blue hover:text-white transition-all"
              title="Planning de revision"
            >
              <Calendar size={12} />
              <span className="hidden sm:inline">Planning</span>
            </button>

            <div className="hidden md:flex items-center gap-2">
              {auth.user?.role === "admin" && (
                <button 
                  onClick={() => router.push("/admin")}
                  className="flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-lg text-[9px] font-bold uppercase tracking-widest hover:bg-muted transition-all"
                >
                  <Settings size={12} />
                  {t("admin.console")}
                </button>
              )}
              <div className="px-3 py-1.5 bg-ensa-blue/5 border border-ensa-blue/10 rounded-lg text-[9px] font-bold uppercase tracking-widest text-ensa-blue flex items-center gap-1.5">
                <Sparkles size={12} />
                {t("chat.assistant_name")}
              </div>
            </div>
          </div>
        </header>

        {/* Messages */}
        <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-6 lg:px-8 space-y-6 custom-scrollbar scroll-smooth">
          {chat.messages.length === 0 && !chat.isLoading && (
            <div className="max-w-3xl mx-auto py-8 animate-in fade-in zoom-in-95 duration-700">
              <div className="bg-card border border-border rounded-3xl p-8 md:p-12 text-center shadow-xl relative overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-1 bg-ensa-blue" />
                <div className="w-16 h-16 bg-ensa-blue/5 rounded-2xl flex items-center justify-center mx-auto mb-8 shadow-inner">
                  <GraduationCap size={32} className="text-ensa-blue" />
                </div>
                <h2 className="font-poppins font-extrabold text-2xl md:text-3xl text-ensa-navy dark:text-white mb-4">{t("common.welcome")}</h2>
                <p className="text-muted-foreground font-medium mb-8 max-w-lg mx-auto leading-relaxed text-sm">
                  {t("chat.welcome_msg")}
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl mx-auto">
                  {EXAMPLES.map((q) => (
                    <button
                      key={q}
                      onClick={() => handleSend(q)}
                      className="group flex items-center justify-between p-4 bg-muted/30 border border-border rounded-2xl hover:border-ensa-blue hover:bg-card hover:shadow-lg transition-all text-left"
                    >
                      <span className="text-[12px] font-semibold text-foreground/75 group-hover:text-ensa-blue">{q}</span>
                      <div className="w-6 h-6 rounded-full bg-ensa-blue/5 flex items-center justify-center group-hover:bg-ensa-blue transition-all">
                        <ChevronRight size={14} className="text-ensa-blue group-hover:text-white transition-transform group-hover:translate-x-0.5" />
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
          
          <div className="max-w-4xl mx-auto w-full space-y-6">
            {chat.messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {chat.isLoading && (
              <div className="flex justify-start">
                <div className="bg-muted/50 p-4 rounded-2xl border border-border shadow-sm">
                  <TypingDots />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Input */}
        <div className="p-4 lg:p-6 bg-gradient-to-t from-background via-background/95 to-transparent sticky bottom-0">
          <div className="max-w-4xl mx-auto relative">
            <ChatInput disabled={chat.isLoading} onCancel={chat.cancelGeneration} onSend={handleSend} />
          </div>
        </div>
      </section>

      {isPlannerOpen && (
        <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm p-3 sm:p-6 overflow-y-auto">
          <div className="mx-auto w-full max-w-4xl rounded-2xl border border-border bg-card shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <h2 className="text-sm font-poppins font-black uppercase tracking-widest text-ensa-navy dark:text-blue-100">
                  Planning de revision
                </h2>
                <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Module separe du chat pour preparer les examens
                </p>
              </div>
              <button
                onClick={() => setIsPlannerOpen(false)}
                className="rounded-lg border border-border p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-all"
                title="Fermer"
              >
                <X size={16} />
              </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 p-4">
              <div className="lg:col-span-2 space-y-4">
                <div className="rounded-xl border border-border bg-muted/20 p-3 space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Examen / Module</label>
                  <input
                    value={plannerExamName}
                    onChange={(e) => setPlannerExamName(e.target.value)}
                    placeholder="Ex: Algorithmique avancee"
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-xs font-semibold outline-none focus:border-ensa-blue"
                  />
                </div>

                <div className="rounded-xl border border-border bg-muted/20 p-3 space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Date examen</label>
                  <input
                    type="date"
                    value={plannerExamDate}
                    onChange={(e) => setPlannerExamDate(e.target.value)}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-xs font-semibold outline-none focus:border-ensa-blue"
                  />
                </div>

                <div className="rounded-xl border border-border bg-muted/20 p-3 space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Temps quotidien (heures)</label>
                  <input
                    type="number"
                    min="0.5"
                    max="12"
                    step="0.5"
                    value={plannerDailyHours}
                    onChange={(e) => setPlannerDailyHours(e.target.value)}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-xs font-semibold outline-none focus:border-ensa-blue"
                  />
                </div>

                <div className="rounded-xl border border-border bg-muted/20 p-3 space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Jours indisponibles</label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {WEEKDAY_CONFIG.map((day) => {
                      const selected = plannerUnavailableDays.includes(day.label);
                      return (
                        <button
                          key={day.label}
                          type="button"
                          aria-pressed={selected}
                          onClick={() => togglePlannerUnavailableDay(day.label)}
                          className={`group flex min-h-[42px] items-center justify-between gap-2 rounded-lg border px-2.5 py-2 text-[10px] font-black uppercase tracking-widest transition-all ${
                            selected
                              ? "border-destructive bg-destructive text-white shadow-[0_0_0_2px_rgba(239,68,68,0.22)]"
                              : "border-border bg-card text-muted-foreground hover:border-ensa-blue/40 hover:text-foreground"
                          }`}
                        >
                          <span>{day.label}</span>
                          {selected && (
                            <span className="flex items-center gap-1 rounded-full bg-white/15 px-1.5 py-0.5 text-[8px] leading-none text-white">
                              <Check className="h-3 w-3" />
                              Indispo
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleGeneratePlan}
                  disabled={plannerLoading}
                  className="w-full rounded-xl bg-ensa-blue px-4 py-2.5 text-[10px] font-black uppercase tracking-[0.18em] text-white hover:bg-ensa-navy transition-all disabled:opacity-60"
                >
                  {plannerLoading ? "Chargement EDT..." : "Generer le planning"}
                </button>

                {plannerError && (
                  <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[11px] font-bold text-destructive">
                    {plannerError}
                  </p>
                )}
              </div>

              <div className="lg:col-span-3 rounded-xl border border-border bg-background p-3">
                {plannerResult.length === 0 ? (
                  <div className="h-full min-h-[280px] flex items-center justify-center rounded-lg border-2 border-dashed border-border/60 text-center px-6">
                    <p className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/70">
                      Definis tes contraintes puis genere ton planning de revision.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
                    <div className="mb-1 flex items-center justify-between rounded-lg bg-ensa-blue/5 border border-ensa-blue/15 px-3 py-2">
                      <p className="text-[10px] font-black uppercase tracking-[0.2em] text-ensa-blue">
                        Plan genere
                      </p>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                        {plannerResult.reduce((sum, item) => sum + item.durationHours, 0).toFixed(1)} h au total
                      </p>
                    </div>

                    {plannerResult.map((item) => (
                      <article
                        key={item.id}
                        className={`rounded-xl border p-3 ${item.isExamDay ? "border-ensa-orange/30 bg-ensa-orange/5" : "border-border bg-card"}`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-[11px] font-black uppercase tracking-[0.14em] text-ensa-navy dark:text-blue-100">
                            {item.dateLabel}
                          </p>
                          <span className="rounded-full bg-ensa-blue/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-ensa-blue">
                            {item.durationHours.toFixed(1)} h
                          </span>
                        </div>
                        <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                          {item.sessionWindow}
                        </p>
                        <p className="mt-2 text-xs font-semibold text-foreground/90">{item.focus}</p>
                        {item.note && <p className="mt-1 text-[10px] font-bold text-muted-foreground">{item.note}</p>}
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <Modal
        isOpen={isPolicyModalOpen}
        onClose={() => setIsPolicyModalOpen(false)}
        title={t("auth.policies")}
      >
        <PrivacyPolicies />
      </Modal>
    </main>
  );
}
