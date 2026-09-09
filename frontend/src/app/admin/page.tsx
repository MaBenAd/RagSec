"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import {
  decideClassChangeRequest,
  deletePublishedTimetable,
  downloadFaqFile,
  deleteFaqFile,
  getFaqFileBlob,
  getAdminClassChangeRequests,
  getPublishedTimetableDetails,
  getPublishedTimetables,
  getFaqFiles,
  getQaPairs,
  getStats,
  previewFaqFile,
  getUsers,
  rebuildVectorstore,
  setQuestionReviewStatus,
  uploadFaq,
  flushCache,
  cleanupOldData,
  deleteUser
} from "@/lib/api";
import type { FaqPreviewResponse } from "@/lib/api";
import { useAuthStore } from "@/store/useAuthStore";
import { ThemeProvider, useTheme } from "@/components/providers/ThemeProvider";
import { EdtForm } from "@/components/admin/EdtForm";
import { TimetableGrid } from "@/components/chat/TimetableGrid";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PdfPreview } from "@/components/admin/PdfPreview";
import { useTranslation } from "react-i18next";
import type { ClassChangeRequest, PublishedTimetable, QaPair, StatsResponse, Timetable, UserActivity } from "@/types";

import { 
  LayoutDashboard, 
  FileText, 
  Calendar, 
  MessageSquare, 
  Users, 
  ArrowLeft,
  Search,
  RefreshCw,
  Trash2,
  Check,
  X,
  Plus,
  Moon,
  Sun,
  AlertCircle,
  ThumbsUp,
  ThumbsDown,
  ChevronRight,
  Database,
  Eraser,
  Eye,
  Download,
  Copy
} from "lucide-react";

export default function AdminPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const auth = useAuthStore();
  const { theme, toggleTheme } = useTheme();

  const [tab, setTab] = useState<"global" | "faq" | "gaps" | "edt" | "qa" | "users">("global");
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [faqFiles, setFaqFiles] = useState<Array<{ name: string; size_kb: number; updated_at: string }>>([]);
  const [publishedTimetables, setPublishedTimetables] = useState<PublishedTimetable[]>([]);
  const [qaPairs, setQaPairs] = useState<QaPair[]>([]);
  const [users, setUsers] = useState<UserActivity[]>([]);
  const [classRequests, setClassRequests] = useState<ClassChangeRequest[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "weak" | "noanswer">("all");
  const [deletingTimetableId, setDeletingTimetableId] = useState<number | null>(null);
  const [deletingUserId, setDeletingUserId] = useState<number | null>(null);
  const [isDeletingUser, setIsDeletingUser] = useState(false);
  const [isRebuildingFaq, setIsRebuildingFaq] = useState(false);
  const [isFlushingCache, setIsFlushingCache] = useState(false);
  const [isCleaningData, setIsCleaningData] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState<string | null>(null);
  const [cleanupCount, setCleanupCount] = useState<number | null>(null);
  const [isUploadingFaq, setIsUploadingFaq] = useState(false);
  const [faqUploadProgress, setFaqUploadProgress] = useState({ done: 0, total: 0 });
  const [loadingTimetableId, setLoadingTimetableId] = useState<number | null>(null);
  const [duplicatingTimetableId, setDuplicatingTimetableId] = useState<number | null>(null);
  const [selectedTimetable, setSelectedTimetable] = useState<Timetable | null>(null);
  const [timetableTemplate, setTimetableTemplate] = useState<Timetable | null>(null);
  const [isTimetableModalOpen, setIsTimetableModalOpen] = useState(false);
  const [loadingFaqPreviewName, setLoadingFaqPreviewName] = useState<string | null>(null);
  const [faqPreview, setFaqPreview] = useState<FaqPreviewResponse | null>(null);
  const [faqPdfPreviewUrl, setFaqPdfPreviewUrl] = useState<string | null>(null);
  const [isFaqPreviewOpen, setIsFaqPreviewOpen] = useState(false);
  const [downloadingFaqName, setDownloadingFaqName] = useState<string | null>(null);
  const [confirmTimetableDelete, setConfirmTimetableDelete] = useState<PublishedTimetable | null>(null);

  useEffect(() => {
    return () => {
      if (faqPdfPreviewUrl) {
        URL.revokeObjectURL(faqPdfPreviewUrl);
      }
    };
  }, [faqPdfPreviewUrl]);

  useEffect(() => {
    useAuthStore.getState().hydrate();
  }, []);

  useEffect(() => {
    if (auth.hydrated && (!auth.token || auth.user?.role !== "admin")) {
      router.replace("/chat");
    }
  }, [auth.hydrated, auth.token, auth.user, router]);

  const load = async () => {
    try {
      const [s, q, u, reqs] = await Promise.all([getStats(), getQaPairs(), getUsers(), getAdminClassChangeRequests("pending")]);
      setStats(s);
      setQaPairs(q);
      setUsers(u);
      setClassRequests(reqs);
      try {
        setFaqFiles(await getFaqFiles());
      } catch {
        setFaqFiles([]);
      }
      try {
        setPublishedTimetables(await getPublishedTimetables());
      } catch {
        setPublishedTimetables([]);
      }
    } catch {
      toast.error("Erreur chargement admin");
    }
  };

  const refreshEdtFiles = async () => {
    setPublishedTimetables(await getPublishedTimetables());
  };

  useEffect(() => {
    if (!auth.hydrated || !auth.token || auth.user?.role !== "admin") return;
    load().catch(() => undefined);
  }, [auth.hydrated, auth.token, auth.user?.role]);

  const onDrop = async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0 || isUploadingFaq || isRebuildingFaq) return;
    try {
      setIsUploadingFaq(true);
      setFaqUploadProgress({ done: 0, total: acceptedFiles.length });
      for (let i = 0; i < acceptedFiles.length; i += 1) {
        const file = acceptedFiles[i];
        await uploadFaq(file, false);
        setFaqUploadProgress({ done: i + 1, total: acceptedFiles.length });
      }
      toast.success("Fichiers FAQ importés");
      setIsRebuildingFaq(true);
      await rebuildVectorstore();
      toast.success("Index FAQ reconstruit");
      setFaqFiles(await getFaqFiles());
    } catch {
      toast.error("Erreur upload FAQ");
    } finally {
      setIsRebuildingFaq(false);
      setIsUploadingFaq(false);
    }
  };

  const dz = useDropzone({
    onDrop,
    disabled: isUploadingFaq || isRebuildingFaq,
    accept: { "application/pdf": [".pdf"], "application/json": [".json"], "text/plain": [".txt"], "text/markdown": [".md"] }
  });

  const filteredQa = useMemo(() => {
    if (filter === "all") return qaPairs;
    if (filter === "weak") {
      return qaPairs.filter((q) => {
        const answer = q.answer ?? "";
        return answer.includes("❌") || answer.toLowerCase().includes("je ne trouve pas");
      });
    }
    return qaPairs.filter((q) => (q.answer ?? "").trim().length < 5);
  }, [qaPairs, filter]);

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) => u.email.toLowerCase().includes(q));
  }, [users, search]);

  const handleDecision = async (requestId: number, decision: "approve" | "reject") => {
    try {
      await decideClassChangeRequest(requestId, decision);
      setClassRequests((prev) => prev.filter((r) => r.id !== requestId));
      setUsers(await getUsers(search));
      toast.success(decision === "approve" ? "Demande approuvée" : "Demande refusée");
    } catch {
      toast.error("Impossible de traiter la demande");
    }
  };

  const handleMarkTreated = async (question: string) => {
    try {
      await setQuestionReviewStatus(question, "treated");
      toast.success("Marqué comme traité");
      load(); // Refresh stats
    } catch {
      toast.error("Erreur lors de la mise à jour");
    }
  };

  const handleFlushCache = async () => {
    if (isFlushingCache) return;
    try {
      setIsFlushingCache(true);
      await flushCache();
      toast.success("Cache Redis purgé");
    } catch {
      toast.error("Erreur purge cache");
    } finally {
      setIsFlushingCache(false);
    }
  };

  const handleCleanupOldData = async (days = 180) => {
    if (isCleaningData) return;
    try {
      setIsCleaningData(true);
      setCleanupMessage(null);
      setCleanupCount(null);
      const result = await cleanupOldData(days);
      setCleanupMessage(result.message);
      setCleanupCount(result.deleted_count);
      toast.success("Nettoyage des données terminé");
    } catch {
      toast.error("Erreur lors du nettoyage des données");
    } finally {
      setIsCleaningData(false);
    }
  };

  const handleDeleteUser = async (userId: number) => {
    if (isDeletingUser) return;
    try {
      setIsDeletingUser(true);
      setDeletingUserId(userId);
      await deleteUser(userId);
      setUsers(await getUsers(search));
      toast.success("Utilisateur supprimé");
    } catch {
      toast.error("Impossible de supprimer l'utilisateur");
    } finally {
      setIsDeletingUser(false);
      setDeletingUserId(null);
    }
  };

  const handleDeletePublishedTimetable = async (timetableId: number) => {
    if (deletingTimetableId !== null) return;

    try {
      setDeletingTimetableId(timetableId);
      await deletePublishedTimetable(timetableId);
      setPublishedTimetables(await getPublishedTimetables());
      setConfirmTimetableDelete(null);
      toast.success("Emploi du temps supprimé");
    } catch {
      toast.error("Impossible de supprimer l'emploi du temps");
    } finally {
      setDeletingTimetableId(null);
    }
  };

  const handleViewPublishedTimetable = async (timetableId: number) => {
    if (loadingTimetableId !== null) return;
    try {
      setLoadingTimetableId(timetableId);
      const timetable = await getPublishedTimetableDetails(timetableId);
      setSelectedTimetable(timetable);
      setIsTimetableModalOpen(true);
    } catch {
      toast.error("Impossible de charger le detail de l'emploi du temps");
    } finally {
      setLoadingTimetableId(null);
    }
  };

  const handleDuplicatePublishedTimetable = async (timetableId: number) => {
    if (duplicatingTimetableId !== null) return;
    try {
      setDuplicatingTimetableId(timetableId);
      const timetable = await getPublishedTimetableDetails(timetableId);
      setTab("edt");
      setTimetableTemplate(timetable);
      toast.success("Modele d'emploi du temps charge dans le formulaire");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      toast.error("Impossible de charger le modele a dupliquer");
    } finally {
      setDuplicatingTimetableId(null);
    }
  };

  const handlePreviewFaq = async (filename: string) => {
    if (loadingFaqPreviewName !== null) return;
    try {
      setLoadingFaqPreviewName(filename);
      const preview = await previewFaqFile(filename);

      if (filename.toLowerCase().endsWith(".pdf")) {
        const pdfBlob = await getFaqFileBlob(filename);
        const objectUrl = URL.createObjectURL(pdfBlob);
        setFaqPdfPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return objectUrl;
        });
        setFaqPreview(preview);
        setIsFaqPreviewOpen(true);
        return;
      }

      setFaqPdfPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setFaqPreview(preview);
      setIsFaqPreviewOpen(true);
    } catch {
      toast.error("Impossible de charger l'apercu du fichier FAQ");
    } finally {
      setLoadingFaqPreviewName(null);
    }
  };

  const handleDownloadFaq = async (filename: string) => {
    if (downloadingFaqName !== null) return;
    try {
      setDownloadingFaqName(filename);
      await downloadFaqFile(filename);
      toast.success("Telechargement demarre");
    } catch {
      toast.error("Impossible de telecharger le fichier FAQ");
    } finally {
      setDownloadingFaqName(null);
    }
  };

  return (
    <main className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-border bg-card px-4 h-16 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <button 
            onClick={() => router.push("/chat")}
            className="p-1.5 border border-border rounded-lg hover:bg-muted transition-all"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-xs font-bold uppercase tracking-widest text-foreground">{t("admin.console")}</h1>
            <p className="text-[9px] font-bold uppercase tracking-tighter text-muted-foreground">Chatbot USMS Control Panel</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2.5">
          <button 
            onClick={toggleTheme}
            className="p-1.5 border border-border rounded-lg hover:bg-muted transition-all"
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          
          <LanguageSwitcher direction="down" align="right" />

          <div className="hidden md:block h-8 w-px bg-border mx-1.5" />
          <div className="hidden md:flex items-center gap-2.5">
            <div className="text-right">
              <p className="text-[11px] font-bold text-foreground">{auth.user?.email}</p>
              <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-tighter">System Administrator</p>
            </div>
            <div className="w-8 h-8 bg-foreground text-background rounded-full flex items-center justify-center font-bold text-xs">
              A
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 flex flex-col md:flex-row min-h-0">
        {/* Nav Sidebar */}
        <nav className="w-full md:w-56 border-b md:border-b-0 md:border-r border-border bg-card p-3 space-y-0.5">
          {[
            { id: "global", label: t("admin.stats"), icon: LayoutDashboard },
            { id: "faq", label: t("admin.faq"), icon: FileText },
            { id: "gaps", label: t("admin.gaps"), icon: AlertCircle },
            { id: "edt", label: t("admin.edt"), icon: Calendar },
            { id: "qa", label: t("admin.qa"), icon: MessageSquare },
            { id: "users", label: t("admin.users"), icon: Users }
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id as any)}
              className={`
                w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-xs font-bold uppercase tracking-tighter transition-all
                ${tab === item.id 
                  ? "bg-foreground text-background shadow-md" 
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"}
              `}
            >
              <item.icon size={16} />
              {item.label}
            </button>
          ))}
        </nav>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 lg:p-8 custom-scrollbar bg-background/50">
          {tab === "global" && stats && (
            <div className="max-w-6xl mx-auto space-y-6 animate-in fade-in duration-500">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard title={t("admin.users")} value={stats.total_users} icon={Users} />
                <StatCard title={t("admin.conversations")} value={stats.total_conversations} icon={MessageSquare} />
                <StatCard 
                  title={t("admin.messages")} 
                  value={stats.total_messages} 
                  icon={FileText} 
                  subtitle={
                    <div className="flex items-center gap-2 mt-1.5">
                      <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
                        <ThumbsUp size={9} fill="currentColor" />
                        <span className="text-[9px] font-bold">{stats.feedback_stats.positive}</span>
                      </div>
                      <div className="flex items-center gap-1 text-red-600 dark:text-red-400">
                        <ThumbsDown size={9} fill="currentColor" />
                        <span className="text-[9px] font-bold">{stats.feedback_stats.negative}</span>
                      </div>
                    </div>
                  }
                />
                <button onClick={() => setTab("gaps")} className="text-left transition-transform hover:scale-[1.01] active:scale-[0.99]">
                  <StatCard title={t("admin.gaps")} value={stats.weak_questions.length} icon={AlertCircle} trend="attention" />
                </button>
              </div>
              
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
                  <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground mb-4 flex items-center gap-1.5">
                    <LayoutDashboard size={12} /> {t("admin.frequent_questions")}
                  </h3>
                  <div className="space-y-3">
                    {stats.top_questions.slice(0, 5).map((q, idx) => (
                      <div key={idx} className="flex items-center justify-between p-3 rounded-lg border border-border hover:border-foreground transition-all group">
                        <span className="text-xs font-medium text-foreground">{q.question}</span>
                        <span className="text-[10px] font-bold bg-muted px-2 py-0.5 rounded-full group-hover:bg-foreground group-hover:text-background transition-all">
                          {q.count} {t("admin.times")}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
                  <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground mb-4 flex items-center gap-1.5">
                    <Database size={12} /> {t("admin.maintenance")}
                  </h3>
                  <div className="space-y-3">
                    <div className="p-3 rounded-lg border border-border flex items-center justify-between">
                      <div>
                        <p className="text-xs font-bold">{t("admin.vector_indexing")}</p>
                        <p className="text-[9px] text-muted-foreground uppercase">{t("admin.vector_indexing_desc")}</p>
                      </div>
                      <button
                        onClick={async () => {
                          setIsRebuildingFaq(true);
                          await rebuildVectorstore();
                          toast.success("Index reconstruit");
                          setIsRebuildingFaq(false);
                        }}
                        disabled={isRebuildingFaq}
                        className="p-1.5 border border-border rounded-md hover:bg-foreground hover:text-background transition-all"
                      >
                        <RefreshCw size={14} className={isRebuildingFaq ? "animate-spin" : ""} />
                      </button>
                    </div>

                    <div className="p-3 rounded-lg border border-border flex items-center justify-between">
                      <div>
                        <p className="text-xs font-bold">{t("admin.response_cache")}</p>
                        <p className="text-[9px] text-muted-foreground uppercase">{t("admin.response_cache_desc")}</p>
                      </div>
                      <button
                        onClick={handleFlushCache}
                        disabled={isFlushingCache}
                        className="p-1.5 border border-border rounded-md hover:bg-red-500 hover:text-white transition-all hover:border-red-500"
                      >
                        <Eraser size={14} className={isFlushingCache ? "animate-pulse" : ""} />
                      </button>
                    </div>

                    <div className="p-3 rounded-lg border border-border flex items-center justify-between">
                      <div>
                        <p className="text-xs font-bold">{t("admin.data_cleanup")}</p>
                        <p className="text-[9px] text-muted-foreground uppercase">{t("admin.data_cleanup_desc")}</p>
                        {cleanupMessage && (
                          <p className="mt-2 text-[10px] text-foreground/80">
                            {cleanupMessage} {cleanupCount !== null && `(${cleanupCount})`}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => handleCleanupOldData(180)}
                        disabled={isCleaningData}
                        className="p-1.5 border border-border rounded-md hover:bg-foreground hover:text-background transition-all"
                      >
                        <Database size={14} className={isCleaningData ? "animate-pulse" : ""} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab === "faq" && (
            <div className="max-w-4xl mx-auto space-y-6 animate-in slide-in-from-bottom-4 duration-500">
              <div 
                {...dz.getRootProps()}
                className={`
                  border-2 border-dashed rounded-2xl p-8 text-center transition-all
                  ${isUploadingFaq || isRebuildingFaq ? "opacity-50 cursor-not-allowed bg-muted" : "border-border hover:border-foreground cursor-pointer bg-card hover:shadow-lg"}
                `}
              >
                <input {...dz.getInputProps()} />
                <div className="w-12 h-12 bg-foreground/5 rounded-xl flex items-center justify-center mx-auto mb-3">
                  <Plus size={24} className="text-foreground/40" />
                </div>
                <p className="text-xs font-bold uppercase tracking-widest mb-1.5">
                  {isUploadingFaq ? "Upload..." : isRebuildingFaq ? "Reconstruction index..." : "Ajouter des documents FAQ"}
                </p>
                <p className="text-[10px] text-muted-foreground">PDF, JSON, TXT ou Markdown</p>
              </div>

              {isUploadingFaq && (
                <div className="bg-card border border-border rounded-lg p-3">
                  <div className="flex justify-between text-[9px] font-bold uppercase mb-1.5">
                    <span>Progression</span>
                    <span>{faqUploadProgress.done}/{faqUploadProgress.total}</span>
                  </div>
                  <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-foreground transition-all duration-500" 
                      style={{ width: `${(faqUploadProgress.done / faqUploadProgress.total) * 100}%` }}
                    />
                  </div>
                </div>
              )}

              {isRebuildingFaq && !isUploadingFaq && (
                <div className="bg-card border border-border rounded-lg p-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  Reconstruction index FAQ en cours...
                </div>
              )}

              <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
                <div className="p-4 border-b border-border flex items-center justify-between bg-muted/30">
                  <h3 className="text-[10px] font-bold uppercase tracking-widest text-foreground">{t("admin.knowledge_files")}</h3>
                  <p className="text-[9px] font-bold text-muted-foreground uppercase">{faqFiles.length} {t("admin.active_files")}</p>
                </div>
                <div className="divide-y divide-border">
                  {faqFiles.map((f) => (
                    <div key={f.name} className="p-3 flex items-center justify-between hover:bg-muted/50 transition-colors group">
                      <div className="flex items-center gap-2.5">
                        <div className="p-1.5 bg-foreground/5 rounded-md">
                          <FileText size={14} className="text-muted-foreground" />
                        </div>
                        <div>
                          <p className="text-xs font-bold text-foreground">{f.name}</p>
                          <p className="text-[9px] font-bold text-muted-foreground uppercase">{f.size_kb} Ko</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => handlePreviewFaq(f.name)}
                          disabled={loadingFaqPreviewName !== null}
                          className="p-1.5 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                          title="Voir l'apercu"
                        >
                          <Eye size={14} />
                        </button>
                        <button
                          onClick={() => handleDownloadFaq(f.name)}
                          disabled={downloadingFaqName !== null}
                          className="p-1.5 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                          title="Telecharger"
                        >
                          <Download size={14} />
                        </button>
                        <button
                          onClick={async () => {
                            await deleteFaqFile(f.name);
                            setFaqFiles(await getFaqFiles());
                          }}
                          className="p-1.5 text-muted-foreground hover:text-destructive transition-colors"
                          title="Supprimer"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                  {faqFiles.length === 0 && (
                    <div className="p-8 text-center text-muted-foreground font-medium text-xs">
                      Aucun document dans la base.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === "gaps" && stats && (
            <div className="max-w-4xl mx-auto space-y-6 animate-in slide-in-from-bottom-4 duration-500">
              <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
                <div className="p-4 border-b border-border flex items-center justify-between bg-muted/30">
                  <h3 className="text-[10px] font-bold uppercase tracking-widest text-foreground">{t("admin.gaps_title")}</h3>
                  <span className="text-[9px] font-bold bg-destructive text-destructive-foreground px-1.5 py-0.5 rounded-md uppercase tracking-tighter">
                    {stats.weak_questions.length} {t("admin.gaps")}
                  </span>
                </div>
                <div className="divide-y divide-border">
                  {stats.weak_questions.map((q, idx) => (
                    <div key={idx} className="p-4 flex flex-col gap-3 hover:bg-muted/30 transition-colors">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-2.5">
                          <div className="p-1.5 bg-destructive/10 text-destructive rounded-md mt-0.5">
                            <AlertCircle size={14} />
                          </div>
                          <div>
                            <p className="text-xs font-bold text-foreground leading-tight">{q.question}</p>
                            <p className="text-[9px] font-bold text-muted-foreground uppercase mt-1">
                              Posée {q.occurrences} {t("admin.times")} • {q.last_seen}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => handleMarkTreated(q.question)}
                          className="flex items-center gap-1.5 border border-border hover:border-foreground px-2 py-1 rounded-md text-[9px] font-bold uppercase tracking-widest transition-all"
                        >
                          <Check size={12} /> {t("admin.treated")}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {tab === "edt" && (
            <div className="max-w-4xl mx-auto space-y-6 animate-in slide-in-from-bottom-4 duration-500">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground mb-4">{t("admin.upload_edt")}</h3>
                <EdtForm onUploaded={refreshEdtFiles} initialTimetableTemplate={timetableTemplate} />
              </div>

              <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
                <div className="p-4 border-b border-border flex items-center justify-between bg-muted/30">
                  <h3 className="text-[10px] font-bold uppercase tracking-widest text-foreground">Emplois du temps publies</h3>
                  <button
                    onClick={refreshEdtFiles}
                    className="p-1.5 border border-border rounded-md hover:bg-muted transition-all"
                  >
                    <RefreshCw size={14} />
                  </button>
                </div>
                <div className="divide-y divide-border">
                  {publishedTimetables.map((tt) => (
                    <div key={tt.id} className="p-3 flex items-center justify-between hover:bg-muted/50 transition-colors">
                      <div className="flex items-center gap-2.5">
                        <div className="p-1.5 bg-foreground/5 rounded-md font-bold text-[10px] uppercase tracking-tighter">
                          {tt.semester}
                        </div>
                        <div>
                          <p className="text-xs font-bold text-foreground">{tt.class_label}</p>
                          <p className="text-[9px] font-bold text-muted-foreground uppercase">
                            {tt.academic_year} • Mis a jour le {new Date(tt.updated_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-md bg-ensa-emerald/10 px-2 py-1 text-[9px] font-bold uppercase tracking-widest text-ensa-emerald">
                          Actif
                        </span>
                        <button
                          onClick={() => handleViewPublishedTimetable(tt.id)}
                          disabled={loadingTimetableId !== null}
                          className="p-1.5 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                          title="Voir le detail"
                        >
                          <Eye size={14} />
                        </button>
                        <button
                          onClick={() => handleDuplicatePublishedTimetable(tt.id)}
                          disabled={duplicatingTimetableId !== null}
                          className="p-1.5 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                          title="Dupliquer dans le formulaire"
                        >
                          <Copy size={14} />
                        </button>
                        <button
                          onClick={() => setConfirmTimetableDelete(tt)}
                          disabled={deletingTimetableId !== null}
                          className="p-1.5 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                          title="Supprimer cet emploi du temps"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                  {publishedTimetables.length === 0 && (
                    <div className="p-8 text-center text-muted-foreground font-medium text-xs">
                      <p className="font-bold uppercase tracking-widest">Aucun emploi du temps publie</p>
                      <p className="mt-2 text-[11px]">Ajoute un EDT avec le formulaire au-dessus pour activer les reponses du chat.</p>
                    </div>
                  )}
                </div>
              </div>

            </div>
          )}

          {tab === "qa" && (
            <div className="max-w-6xl mx-auto space-y-4 animate-in slide-in-from-bottom-4 duration-500">
              <div className="flex flex-col sm:flex-row gap-1.5">
                {[
                  { id: "all", label: t("admin.all_questions") },
                  { id: "weak", label: t("admin.weak_answers") },
                  { id: "noanswer", label: t("admin.no_answer") }
                ].map((f) => (
                  <button
                    key={f.id}
                    onClick={() => setFilter(f.id as any)}
                    className={`
                      px-3 py-1.5 rounded-lg text-[9px] font-bold uppercase tracking-widest border transition-all
                      ${filter === f.id 
                        ? "bg-foreground text-background border-foreground shadow-md" 
                        : "bg-card text-muted-foreground border-border hover:border-foreground"}
                    `}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-left min-w-[800px]">
                    <thead>
                      <tr className="border-b border-border bg-muted/30">
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{t("admin.user")}</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{t("admin.question")}</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{t("admin.answer")}</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground text-center">{t("admin.opinion")}</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{t("admin.date")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filteredQa.map((q, idx) => (
                        <tr key={idx} className="hover:bg-muted/30 transition-colors">
                          <td className="p-3 text-[11px] font-bold truncate max-w-[150px]">{q.email}</td>
                          <td className="p-3 text-[11px] text-foreground font-medium max-w-[200px] truncate">{q.question}</td>
                          <td className="p-3 text-[11px] text-muted-foreground line-clamp-2 max-w-md">{q.answer}</td>
                          <td className="p-3 text-center">
                            {q.feedback === 1 ? (
                              <ThumbsUp size={12} className="text-green-500 mx-auto" fill="currentColor" />
                            ) : q.feedback === -1 ? (
                              <ThumbsDown size={12} className="text-red-500 mx-auto" fill="currentColor" />
                            ) : (
                              <span className="text-[9px] text-muted-foreground/30">-</span>
                            )}
                          </td>
                          <td className="p-3 text-[9px] font-bold uppercase text-muted-foreground/60">
                            {new Date(q.created_at).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {tab === "users" && (
            <div className="max-w-6xl mx-auto space-y-6 animate-in slide-in-from-bottom-4 duration-500">
              <div className="relative group">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-foreground transition-colors" size={16} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("admin.search_user")}
                  className="w-full bg-card border border-border pl-10 pr-3.5 py-3 rounded-xl text-xs outline-none focus:ring-1 focus:ring-foreground/10 focus:border-foreground transition-all shadow-sm"
                />
              </div>

              {classRequests.length > 0 && (
                <div className="bg-foreground text-background rounded-xl p-6 shadow-2xl relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-background/10 rounded-full -mr-12 -mt-12 blur-2xl" />
                  <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] mb-4 flex items-center gap-1.5 opacity-80">
                    <Check size={12} /> {t("admin.class_requests")}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {classRequests.map((req) => (
                      <div key={req.id} className="bg-background/10 backdrop-blur-md rounded-lg p-4 border border-white/10 group">
                        <p className="font-bold text-xs mb-1">{req.user_email}</p>
                        <div className="flex items-center gap-1.5 text-[9px] font-bold uppercase opacity-60 mb-2.5">
                          <span>{req.current_class_label || "None"}</span>
                          <ChevronRight size={8} />
                          <span className="text-white bg-white/20 px-1.5 py-0.5 rounded">{req.requested_class_label}</span>
                        </div>
                        {req.reason && <p className="text-[11px] mb-3 italic opacity-80 line-clamp-2">&quot;{req.reason}&quot;</p>}
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => handleDecision(req.id, "approve")}
                            className="flex-1 bg-white text-black py-1.5 rounded-md text-[9px] font-bold uppercase tracking-widest hover:bg-opacity-90 transition-all flex items-center justify-center gap-1.5"
                          >
                            <Check size={12} /> {t("admin.approve")}
                          </button>
                          <button
                            onClick={() => handleDecision(req.id, "reject")}
                            title={t("admin.reject")}
                            className="px-3 border border-white/20 rounded-md hover:bg-white/10 transition-all"
                          >
                            <X size={12} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-left min-w-[600px]">
                    <thead>
                      <tr className="border-b border-border bg-muted/30">
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{t("admin.user")}</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{t("admin.role")}</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{t("common.filiere")}</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground text-center">Convs</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground text-center">Msgs</th>
                        <th className="p-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filteredUsers.map((u) => (
                        <tr key={u.id} className="hover:bg-muted/30 transition-colors">
                          <td className="p-3 text-[11px] font-bold">{u.email}</td>
                          <td className="p-3">
                            <span className={`px-1.5 py-0.5 rounded-md text-[9px] font-bold uppercase ${u.role === 'admin' ? 'bg-foreground text-background' : 'bg-muted text-muted-foreground'}`}>
                              {u.role}
                            </span>
                          </td>
                          <td className="p-3 text-[11px] font-bold uppercase">{u.class_label ?? "-"}</td>
                          <td className="p-3 text-[11px] font-bold text-center">{u.conversations_count}</td>
                          <td className="p-3 text-[11px] font-bold text-center">{u.messages_count}</td>
                          <td className="p-3 text-right">
                            <button
                              onClick={() => handleDeleteUser(u.id)}
                              disabled={isDeletingUser && deletingUserId === u.id}
                              className="inline-flex items-center gap-2 px-3 py-1 rounded-md border border-red-500 text-red-500 hover:bg-red-500 hover:text-white transition-all text-[9px] font-bold uppercase"
                            >
                              <Trash2 size={12} /> {t("admin.delete")}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {isTimetableModalOpen && selectedTimetable && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm p-3 sm:p-6 overflow-y-auto">
          <div className="mx-auto max-w-6xl bg-background border border-border rounded-2xl shadow-2xl">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-widest">Detail de l&apos;emploi du temps publie</h3>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">
                  {selectedTimetable.class_label} • {selectedTimetable.semester} • {selectedTimetable.academic_year}
                </p>
              </div>
              <button
                onClick={() => {
                  setIsTimetableModalOpen(false);
                  setSelectedTimetable(null);
                }}
                className="p-1.5 border border-border rounded-lg hover:bg-muted transition-all"
                title="Fermer"
              >
                <X size={14} />
              </button>
            </div>
            <div className="p-4">
              <TimetableGrid timetable={selectedTimetable} layout="rows" showLayoutToggle={true} />
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(confirmTimetableDelete)}
        title="Supprimer l'EDT"
        description={
          confirmTimetableDelete
            ? `L'emploi du temps ${confirmTimetableDelete.class_label} (${confirmTimetableDelete.semester}) sera supprime definitivement.`
            : ""
        }
        confirmLabel="Supprimer"
        loading={deletingTimetableId !== null}
        onCancel={() => deletingTimetableId === null && setConfirmTimetableDelete(null)}
        onConfirm={() => {
          if (confirmTimetableDelete) handleDeletePublishedTimetable(confirmTimetableDelete.id);
        }}
      />

      {isFaqPreviewOpen && faqPreview && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm p-3 sm:p-6 overflow-y-auto">
          <div className="mx-auto max-w-4xl bg-background border border-border rounded-2xl shadow-2xl">
            <div className="p-4 border-b border-border flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-xs font-bold uppercase tracking-widest">Apercu du fichier FAQ</h3>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1 truncate">
                  {faqPreview.filename} • {faqPreview.file_type} • {faqPreview.snippet_count} extraits
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleDownloadFaq(faqPreview.filename)}
                  className="p-1.5 border border-border rounded-lg hover:bg-muted transition-all"
                  title="Telecharger"
                >
                  <Download size={14} />
                </button>
                <button
                  onClick={() => {
                    setIsFaqPreviewOpen(false);
                    setFaqPreview(null);
                    setFaqPdfPreviewUrl((prev) => {
                      if (prev) URL.revokeObjectURL(prev);
                      return null;
                    });
                  }}
                  className="p-1.5 border border-border rounded-lg hover:bg-muted transition-all"
                  title="Fermer"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
            <div className="p-4">
              {faqPreview.file_type === "pdf" ? (
                <div className="space-y-2">
                  <div className="rounded-xl border border-border bg-muted/30 p-3 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    Apercu PDF (fichier original)
                  </div>
                  {faqPdfPreviewUrl ? (
                    <PdfPreview url={faqPdfPreviewUrl} filename={faqPreview.filename} />
                  ) : (
                    <div className="h-[70vh] rounded-xl border border-border bg-white flex items-center justify-center text-xs font-bold text-muted-foreground uppercase tracking-widest">
                      Chargement du PDF...
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <div className="rounded-xl border border-border bg-muted/30 p-3 text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
                    {faqPreview.truncated ? "Apercu tronque (partiel)" : "Apercu complet"}
                  </div>
                  <pre className="max-h-[60vh] overflow-auto text-[11px] font-mono leading-relaxed p-4 rounded-xl border border-border bg-card text-foreground custom-scrollbar whitespace-pre-wrap">
                    {faqPreview.text}
                  </pre>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function StatCard({ title, value, icon: Icon, trend, subtitle }: { title: string; value: number; icon: any; trend?: string; subtitle?: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-sm group hover:border-foreground transition-all h-full">
      <div className="flex justify-between items-start mb-3">
        <div className="p-2 bg-muted rounded-lg group-hover:bg-foreground group-hover:text-background transition-all">
          <Icon size={16} />
        </div>
        {trend === "attention" && value > 0 && (
          <span className="text-[9px] font-bold text-destructive uppercase tracking-widest animate-pulse">{t("admin.attention", { defaultValue: "Attention" })}</span>
        )}
      </div>
      <p className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-0.5">{title}</p>
      <p className="text-2xl font-bold tracking-tighter text-foreground">{value}</p>
      {subtitle}
    </div>
  );
}
