"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuthStore } from "@/store/useAuthStore";
import { useTheme } from "@/components/providers/ThemeProvider";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { 
  getMeActivity, 
  deleteMeAccount, 
  getMyClassChangeRequests, 
  requestClassChange, 
  getEdtClasses, 
  getMeTimetable, 
  getConversations, 
  deleteConversation, 
  exportMyData 
} from "@/lib/api";
import type { ClassChangeRequest, Timetable } from "@/types";
import { TimetableGrid } from "@/components/chat/TimetableGrid";
import { formatClassLabel } from "@/lib/timetable";
import Modal from "@/components/Modal";
import PrivacyPolicies from "@/components/PrivacyPolicies";
import { 
  User, 
  Mail, 
  Calendar, 
  ShieldCheck, 
  Trash2, 
  LogOut, 
  ChevronLeft, 
  Activity, 
  GraduationCap, 
  Clock,
  ExternalLink,
  AlertTriangle,
  ArrowRight,
  Sun,
  Moon,
  Info,
  Download,
  Settings,
  Lock,
  Globe,
  Database,
  History,
  Layout,
  ChevronDown
} from "lucide-react";

function formatProfileName(email: string): string {
  const local = email.split("@")[0] || "";
  if (/^ui\d+$/i.test(local) || !local) return "Etudiant ENSA";
  const pieces = local
    .split(/[._-]+/)
    .map((piece) => piece.replace(/[^a-zA-ZÀ-ÿ]/g, ""))
    .filter(Boolean);
  if (pieces.length === 0) return "Etudiant ENSA";
  return pieces.map((piece) => piece.charAt(0).toUpperCase() + piece.slice(1)).join(" ");
}

const ENGINEERING_TRACKS = ["IACS", "TDI", "G2ER", "IAA"] as const;
const PREPA_TRACKS = ["2AP"] as const;
const ENGINEERING_SEMESTERS = ["S1", "S2", "S3", "S4", "S5", "S6"] as const;
const PREPA_SEMESTERS = ["S1", "S2", "S3", "S4"] as const;

function getCurrentAcademicYear(now = new Date()): string {
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const start = month >= 9 ? year : year - 1;
  return `${start}-${start + 1}`;
}

function normalizeClassLabelValue(label: string): string {
  return label.trim().replace(/\s+/g, "_").toUpperCase();
}

function toCanonicalClassLabel(label: string): string {
  return label.trim().replace(/\s+/g, "_");
}

function buildDefaultClassOptions(): string[] {
  const academicYear = getCurrentAcademicYear();
  const prepa = PREPA_TRACKS.flatMap((track) =>
    PREPA_SEMESTERS.map((semester) => `${track}_${academicYear}_${semester}`)
  );
  const engineering = ENGINEERING_TRACKS.flatMap((track) =>
    ENGINEERING_SEMESTERS.map((semester) => `${track}_${academicYear}_${semester}`)
  );
  return [...prepa, ...engineering];
}

const DEFAULT_CLASS_OPTIONS = buildDefaultClassOptions();

export default function ProfilePage() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const auth = useAuthStore();
  const { theme, toggleTheme } = useTheme();
  
  const [activity, setActivity] = useState<{ day: string; count: number }[]>([]);
  const [timetable, setTimetable] = useState<Timetable | null>(null);
  const [myRequests, setMyRequests] = useState<ClassChangeRequest[]>([]);
  const [classOptions, setClassOptions] = useState<string[]>(DEFAULT_CLASS_OPTIONS);
  const [requestTarget, setRequestTarget] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isPolicyModalOpen, setIsPolicyModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"dashboard" | "security">("dashboard");

  useEffect(() => {
    useAuthStore.getState().hydrate();
  }, []);

  useEffect(() => {
    if (auth.hydrated && !auth.token) {
      router.replace("/login");
    }
  }, [auth.hydrated, auth.token, router]);

  useEffect(() => {
    if (!auth.token || !auth.user) return;
    
    getMeActivity().then(setActivity).catch(() => {});
    getMeTimetable().then(setTimetable).catch(() => {});
    getMyClassChangeRequests().then(setMyRequests).catch(() => {});
    getEdtClasses().then(classes => {
      const published = classes.map((c) => toCanonicalClassLabel(c.label));
      setClassOptions(Array.from(new Set([...DEFAULT_CLASS_OPTIONS, ...published])));
    }).catch(() => {});
  }, [auth.token, auth.user]);

  if (!auth.user) return null;

  const email = auth.user.email || "";
  const fullName = formatProfileName(email);
  const avatarLetter = fullName.charAt(0).toUpperCase() || "E";
  const profileClassLabel = auth.user.class_label ? formatClassLabel(auth.user.class_label) : t("profile.not_defined");
  const currentClassValue = auth.user.class_label ? normalizeClassLabelValue(auth.user.class_label) : "";

  const handleLogout = async () => {
    await auth.logout();
    router.push("/login");
  };

  const handleDeleteAccount = async () => {
    try {
      setIsDeleting(true);
      await deleteMeAccount();
      toast.success(t("profile.account_deleted"));
      await auth.logout();
      router.push("/login");
    } catch {
      toast.error(t("profile.delete_error"));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleClearHistory = async () => {
    if (!confirm(t("profile.clear_history_confirm"))) return;
    try {
      setIsClearingHistory(true);
      const conversations = await getConversations();
      await Promise.allSettled(conversations.map((conv) => deleteConversation(conv.id)));
      setActivity([]);
      toast.success(t("profile.history_cleared"));
    } catch {
      toast.error(t("profile.history_clear_error"));
    } finally {
      setIsClearingHistory(false);
    }
  };

  const handleExportData = async () => {
    try {
      setIsExporting(true);
      const data = await exportMyData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `my_data_${auth.user?.email}_${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success(t("auth.export_success"));
    } catch {
      toast.error(t("auth.export_failed"));
    } finally {
      setIsExporting(false);
    }
  };

  const submitClassRequest = async () => {
    if (!requestTarget) return;
    try {
      const req = await requestClassChange(requestTarget);
      setMyRequests([req, ...myRequests]);
      setRequestTarget("");
      toast.success(t("chat.request_sent"));
    } catch (e) {
      toast.error(t("chat.request_error"));
    }
  };

  const pendingRequest = myRequests.find(r => r.status === "pending");

  return (
    <div className="min-h-screen bg-muted/30 text-foreground font-inter">
      {/* Dynamic Header */}
      <div className="bg-ensa-navy pt-12 pb-24 relative overflow-hidden">
         <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_30%,_rgba(59,130,246,0.2)_0%,_transparent_50%)]" />
         <div className="absolute inset-0 bg-[linear-gradient(135deg,_rgba(255,255,255,0.05)_0%,_transparent_100%)]" />
         
         <div className="max-w-6xl mx-auto px-4 relative z-10">
            <button 
              onClick={() => router.back()}
              className="group mb-8 flex items-center gap-2 text-white/70 hover:text-white transition-all bg-white/5 hover:bg-white/10 px-4 py-2 rounded-xl border border-white/10"
              aria-label={t("common.back_to_chat")}
            >
              <ChevronLeft size={18} className="group-hover:-translate-x-0.5 transition-transform" />
              <span className="text-sm font-bold uppercase tracking-widest">{t("common.back_to_chat")}</span>
            </button>

            <div className="flex flex-col md:flex-row items-center gap-8 md:items-end">
               <div className="w-32 h-32 rounded-[32px] bg-white text-ensa-navy flex items-center justify-center text-5xl font-black shadow-2xl border-4 border-ensa-blue/20 rotate-3 hover:rotate-0 transition-transform duration-500">
                  {avatarLetter}
               </div>
               <div className="text-center md:text-left space-y-2">
                  <div className="flex flex-wrap items-center justify-center md:justify-start gap-3">
                    <h1 className="text-4xl font-poppins font-black tracking-tighter text-white uppercase">{fullName}</h1>
                    <span className="bg-ensa-emerald/20 text-ensa-emerald px-4 py-1 rounded-full text-[10px] font-black uppercase tracking-[0.2em] border border-ensa-emerald/30 backdrop-blur-md">
                      {auth.user.role}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center justify-center md:justify-start gap-4 text-white/60">
                    <div className="flex items-center gap-2">
                       <Mail size={16} className="text-ensa-blue" />
                       <span className="text-sm font-bold">{auth.user.email}</span>
                    </div>
                    <div className="flex items-center gap-2">
                       <GraduationCap size={16} className="text-ensa-blue" />
                       <span className="text-sm font-bold tracking-widest uppercase">
                         {profileClassLabel}
                       </span>
                    </div>
                  </div>
               </div>
            </div>
         </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 -mt-12 relative z-20 pb-20">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Left Column: Quick Stats & Navigation */}
          <div className="lg:col-span-4 space-y-6">
            {/* Quick Actions Card */}
            <div className="bg-card border border-border rounded-3xl p-6 shadow-xl space-y-4">
               <div className="flex items-center gap-3 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-ensa-blue/10 text-ensa-blue flex items-center justify-center">
                    <Settings size={18} />
                  </div>
                  <h3 className="text-sm font-black uppercase tracking-widest">{t("profile.quick_settings")}</h3>
               </div>

               <div className="space-y-2">
                  <div className="flex items-center justify-between p-3.5 rounded-2xl bg-muted/30 border border-border/50 group transition-all hover:bg-muted/50">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-lg ${theme === "dark" ? "bg-ensa-orange/10 text-ensa-orange" : "bg-ensa-navy/10 text-ensa-navy"}`}>
                        {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
                      </div>
                      <span className="text-xs font-bold">{t("profile.dark_mode")}</span>
                    </div>
                    <button 
                      onClick={toggleTheme}
                      className={`w-12 h-6 rounded-full transition-all relative ${theme === "dark" ? "bg-ensa-blue" : "bg-muted-foreground/30"}`}
                      aria-label={t("profile.dark_mode")}
                    >
                      <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${theme === "dark" ? "right-1.5" : "left-1.5"}`} />
                    </button>
                  </div>

                  <div className="p-3.5 rounded-2xl bg-muted/30 border border-border/50 space-y-3 transition-all hover:bg-muted/50">
                    <div className="flex items-center gap-3">
                       <div className="p-2 rounded-lg bg-ensa-emerald/10 text-ensa-emerald">
                          <Globe size={18} />
                       </div>
                       <span className="text-xs font-bold">{t("profile.select_language")}</span>
                    </div>
                    <LanguageSwitcher direction="up" align="left" fullWidth />
                  </div>
               </div>

               <button 
                onClick={handleLogout}
                aria-label="Déconnexion"
                data-testid="logout-button"
                className="w-full flex items-center justify-between p-4 rounded-2xl bg-muted/50 hover:bg-destructive/10 hover:text-destructive transition-all group"
               >
                 <div className="flex items-center gap-3">
                   <LogOut size={18} />
                   <span className="text-xs font-bold uppercase tracking-widest">{t("common.logout")}</span>
                 </div>
                 <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity" />
               </button>
            </div>

            {/* Account Info Stats */}
            <div className="bg-card border border-border rounded-3xl p-6 shadow-xl">
               <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-muted/30 rounded-2xl border border-border/50">
                    <p className="text-[9px] font-black text-muted-foreground uppercase tracking-widest mb-2">{t("profile.joined")}</p>
                    <p className="text-sm font-bold text-ensa-navy dark:text-blue-100">
                      {new Date(auth.user.created_at || Date.now()).toLocaleDateString(i18n.language === "en" ? "en-US" : i18n.language === "ar" ? "ar-MA" : "fr-FR", { month: 'long', year: 'numeric' })}
                    </p>
                  </div>
                  <div className="p-4 bg-muted/30 rounded-2xl border border-border/50">
                    <p className="text-[9px] font-black text-muted-foreground uppercase tracking-widest mb-2">{t("profile.status")}</p>
                    <div className="flex items-center gap-2">
                       <span className="w-2 h-2 rounded-full bg-ensa-emerald animate-pulse" />
                       <span className="text-sm font-bold uppercase tracking-tighter text-ensa-emerald">Online</span>
                    </div>
                  </div>
               </div>
            </div>
          </div>

          {/* Center Column: Main Content */}
          <div className="lg:col-span-8 space-y-6">
            
            {/* Main Tabs/Sections */}
            <div className="bg-card border border-border rounded-[32px] p-1 shadow-xl flex gap-1">
               <button 
                onClick={() => setActiveTab("dashboard")}
                className={`flex-1 py-3.5 rounded-[28px] text-xs font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${
                  activeTab === "dashboard" 
                  ? "bg-ensa-blue text-white shadow-lg shadow-ensa-blue/20" 
                  : "hover:bg-muted text-muted-foreground"
                }`}
               >
                  <Layout size={16} />
                  <span>{t("common.dashboard")}</span>
               </button>
               <button 
                onClick={() => setActiveTab("security")}
                className={`flex-1 py-3.5 rounded-[28px] text-xs font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${
                  activeTab === "security" 
                  ? "bg-ensa-blue text-white shadow-lg shadow-ensa-blue/20" 
                  : "hover:bg-muted text-muted-foreground"
                }`}
               >
                  <Lock size={16} />
                  <span>{t("profile.security")}</span>
               </button>
            </div>

            {/* Dashboard Content */}
            {activeTab === "dashboard" && (
              <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
                  
                  {/* Activity Visualizer */}
                  <div className="bg-card border border-border rounded-[32px] p-8 shadow-xl relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none">
                       <Activity size={120} />
                    </div>
                    <div className="flex items-center justify-between mb-10">
                      <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-2xl bg-ensa-blue/10 text-ensa-blue flex items-center justify-center">
                          <Activity size={24} />
                        </div>
                        <div>
                          <h2 className="text-xl font-poppins font-black tracking-tight uppercase">{t("profile.activity_title")}</h2>
                          <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">{t("profile.last_30_days")}</p>
                        </div>
                      </div>
                    </div>

                    <div className="h-48 flex items-end gap-1.5 px-2">
                      {activity.length > 0 ? (
                        activity.map((day, idx) => {
                          const max = Math.max(...activity.map(d => d.count), 1);
                          const height = Math.max((day.count / max) * 100, 4);
                          return (
                            <div key={idx} className="flex-1 group relative">
                              <div 
                                className={`w-full bg-ensa-blue/20 rounded-t-lg transition-all duration-500 cursor-pointer group-hover:bg-ensa-blue group-hover:shadow-lg group-hover:shadow-ensa-blue/30`}
                                style={{ height: `${height}%` }}
                              />
                              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-3 px-3 py-2 bg-ensa-navy text-white text-[10px] font-black rounded-xl opacity-0 group-hover:opacity-100 transition-all scale-75 group-hover:scale-100 whitespace-nowrap pointer-events-none z-50 border border-white/10 shadow-2xl">
                                {day.count} {t("common.messages", { defaultValue: "messages" })}<br/>
                                <span className="text-white/50 text-[8px] tracking-widest uppercase">{day.day}</span>
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div className="w-full h-full flex flex-col items-center justify-center border-2 border-dashed border-border rounded-3xl bg-muted/10">
                          <History size={40} className="text-muted-foreground/30 mb-4" />
                          <p className="text-xs font-black uppercase tracking-widest text-muted-foreground/50">{t("profile.no_activity")}</p>
                        </div>
                      )}
                    </div>
                    <div className="flex justify-between mt-6 pt-4 border-t border-border/30 text-[10px] font-black text-muted-foreground/40 uppercase tracking-[0.3em] px-2">
                    <span>{t("profile.history_origin")}</span>
                    <span>{t("profile.now")}</span>
                    </div>                  </div>

                  {/* Timetable Section */}
                  {timetable && (
                    <div className="bg-card border border-border rounded-[40px] p-1 shadow-2xl overflow-hidden animate-in fade-in slide-in-from-bottom-8 duration-1000 delay-300">
                      <div className="p-8">
                         <div className="flex items-center gap-3 mb-8">
                            <div className="w-12 h-12 rounded-2xl bg-ensa-blue text-white flex items-center justify-center shadow-lg">
                              <Calendar size={24} />
                            </div>
                            <div>
                              <h2 className="text-2xl font-poppins font-black tracking-tight uppercase text-ensa-navy dark:text-blue-100">{t("profile.my_schedule")}</h2>
                              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">{profileClassLabel}</p>
                            </div>
                         </div>
                         <TimetableGrid timetable={timetable} />
                      </div>
                    </div>
                  )}
              </div>
            )}

            {/* Security & Privacy Content */}
            {activeTab === "security" && (
              <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Compliance & Data Card */}
                    <div className="bg-card border border-border rounded-[32px] p-8 shadow-xl space-y-6">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-ensa-emerald/10 text-ensa-emerald flex items-center justify-center">
                          <Database size={20} />
                        </div>
                        <h3 className="text-sm font-black uppercase tracking-widest">{t("profile.data_management")}</h3>
                      </div>

                      <div className="space-y-3">
                        <button 
                          onClick={handleExportData}
                          disabled={isExporting}
                          className="w-full flex items-center justify-between p-4 rounded-2xl bg-muted/30 border border-border/50 hover:bg-ensa-blue/5 hover:border-ensa-blue/30 hover:text-ensa-blue transition-all group disabled:opacity-50"
                        >
                          <div className="flex items-center gap-3">
                            <Download size={18} />
                            <span className="text-xs font-bold">{t("auth.export_data")}</span>
                          </div>
                          <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 transition-all -translate-x-2 group-hover:translate-x-0" />
                        </button>

                        <button 
                          onClick={handleClearHistory}
                          disabled={isClearingHistory}
                          className="w-full flex items-center justify-between p-4 rounded-2xl bg-muted/30 border border-border/50 hover:bg-ensa-orange/5 hover:border-ensa-orange/30 hover:text-ensa-orange transition-all group disabled:opacity-50"
                        >
                          <div className="flex items-center gap-3">
                            <Trash2 size={18} />
                            <span className="text-xs font-bold">{t("profile.clear_history")}</span>
                          </div>
                          <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 transition-all -translate-x-2 group-hover:translate-x-0" />
                        </button>
                      </div>
                    </div>

                    {/* Danger Zone */}
                    <div className="bg-card border border-border rounded-[32px] p-8 shadow-xl space-y-6 border-destructive/10 bg-destructive/[0.02]">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-destructive/10 text-destructive flex items-center justify-center">
                          <AlertTriangle size={20} />
                        </div>
                        <h3 className="text-sm font-black uppercase tracking-widest text-destructive">{t("profile.danger_zone")}</h3>
                      </div>

                      <div className="space-y-4">
                        <p className="text-[10px] font-medium text-muted-foreground leading-relaxed">
                          {t("profile.danger_hint")}
                        </p>
                        
                        {showDeleteConfirm ? (
                          <div className="space-y-3 animate-in fade-in slide-in-from-top-2">
                             <div className="flex gap-2">
                              <button 
                                onClick={() => setShowDeleteConfirm(false)}
                                className="flex-1 bg-card border border-border py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-muted transition-all"
                              >
                                {t("common.cancel")}
                              </button>
                              <button 
                                onClick={handleDeleteAccount}
                                disabled={isDeleting}
                                className="flex-1 bg-destructive text-white py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-destructive/20 hover:bg-red-700 transition-all disabled:opacity-50"
                              >
                                {isDeleting ? "..." : t("common.confirm")}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button 
                            onClick={() => setShowDeleteConfirm(true)}
                            className="w-full flex items-center justify-center gap-3 p-4 rounded-2xl bg-destructive/10 border border-destructive/20 text-destructive hover:bg-destructive text-xs font-black uppercase tracking-widest transition-all hover:text-white group"
                          >
                            <Trash2 size={18} />
                            <span>{t("profile.delete_account")}</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Security Policy Card */}
                  <div className="bg-card border border-border rounded-[32px] p-8 shadow-xl space-y-6">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-ensa-blue/10 text-ensa-blue flex items-center justify-center">
                        <ShieldCheck size={20} />
                      </div>
                      <h3 className="text-sm font-black uppercase tracking-widest">{t("profile.active_protection")}</h3>
                    </div>
                    
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                       <div className="p-4 rounded-2xl bg-ensa-emerald/5 border border-ensa-emerald/20 space-y-1">
                          <p className="text-[10px] font-black text-ensa-emerald uppercase tracking-widest">{t("profile.secure_session")}</p>
                          <p className="text-xs font-medium text-foreground/70">{t("profile.secure_session_hint")}</p>
                       </div>
                       <div className="p-4 rounded-2xl bg-ensa-blue/5 border border-ensa-blue/20 space-y-1">
                          <p className="text-[10px] font-black text-ensa-blue uppercase tracking-widest">{t("profile.prompt_guard")}</p>
                          <p className="text-xs font-medium text-foreground/70">{t("profile.prompt_guard_hint")}</p>
                       </div>
                    </div>

                    <div
                      onClick={() => setIsPolicyModalOpen(true)}
                      className="flex items-center justify-between p-4 rounded-2xl bg-muted/30 border border-border/50 hover:bg-muted transition-all cursor-pointer group"
                    >
                      <div className="flex items-center gap-3 text-xs font-bold">
                        <Info size={18} className="text-ensa-blue" />
                        <span className="uppercase tracking-widest">{t("profile.privacy_policy")}</span>
                      </div>
                      <ExternalLink size={14} className="text-muted-foreground opacity-50 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </div>

                  {/* Filière Management (Secondary in Security) */}
                  <div className="bg-card border border-border rounded-[32px] p-8 shadow-xl space-y-6">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-ensa-blue/10 text-ensa-blue flex items-center justify-center">
                          <GraduationCap size={20} />
                        </div>
                        <h3 className="text-sm font-black uppercase tracking-widest">{t("profile.academic_request")}</h3>
                    </div>
                    
                    <div className="flex flex-col sm:flex-row items-center gap-6">
                      <div className="flex-1 w-full p-6 rounded-2xl bg-muted/30 border border-border/50">
                        <p className="text-[9px] font-black text-muted-foreground uppercase tracking-widest mb-1">{t("profile.current_filiere")}</p>
                        <p className="text-lg font-poppins font-black text-ensa-navy dark:text-blue-100">
                          {profileClassLabel}
                        </p>
                      </div>

                      <div className="flex-1 w-full">
                        {pendingRequest ? (
                          <div className="bg-ensa-orange/10 border border-ensa-orange/20 p-6 rounded-2xl flex items-center gap-4 animate-pulse">
                            <Clock size={20} className="text-ensa-orange shrink-0" />
                            <div className="min-w-0">
                              <p className="text-[10px] font-black text-ensa-orange uppercase tracking-widest truncate">{t("profile.request_pending")}</p>
                              <p className="text-[8px] font-bold text-ensa-orange/70 uppercase truncate">Vers {formatClassLabel(pendingRequest.requested_class_label)}</p>
                            </div>
                          </div>
                        ) : (
                          <div className="space-y-3">
                             <div className="relative">
                                <select
                                  value={requestTarget}
                                  onChange={(e) => setRequestTarget(e.target.value)}
                                  className="w-full bg-card border border-border rounded-xl p-3 text-[10px] font-black uppercase tracking-widest outline-none cursor-pointer appearance-none transition-all"
                                >
                                  <option value="">{t("chat.change_filiere")}</option>
                                  {classOptions
                                    .filter((f) => normalizeClassLabelValue(f) !== currentClassValue)
                                    .map((f) => <option key={f} value={f}>{formatClassLabel(f)}</option>)}
                                </select>
                                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
                                   <ChevronDown size={14} />
                                </div>
                             </div>
                             {requestTarget && (
                              <button
                                onClick={submitClassRequest}
                                className="w-full bg-ensa-blue text-white py-3 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] hover:bg-ensa-navy transition-all"
                              >
                                {t("chat.confirm_change")}
                              </button>
                             )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <Modal
        isOpen={isPolicyModalOpen}
        onClose={() => setIsPolicyModalOpen(false)}
        title={t("auth.policies")}
      >
        <PrivacyPolicies />
      </Modal>

      {/* Footer Branding */}
      <div className="max-w-6xl mx-auto px-4 py-12 text-center border-t border-border/30 opacity-40">
          <div className="flex items-center justify-center gap-3 mb-4">
             <GraduationCap size={20} />
             <span className="text-[10px] font-black uppercase tracking-[0.5em]">Chatbot USMS · AI Agent</span>
          </div>
          <p className="text-[9px] font-bold uppercase tracking-widest">© {new Date().getFullYear()} ENSA Beni Mellal</p>
      </div>
    </div>
  );
}
