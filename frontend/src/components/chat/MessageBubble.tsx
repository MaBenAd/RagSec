"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Message } from "@/types";
import { useChatStore } from "@/store/useChatStore";
import { useTranslation } from "react-i18next";
import { verifySecurityCitation } from "@/lib/security-api";
import { TimetableGrid } from "./TimetableGrid";
import { User, Bot, Sparkles, ThumbsUp, ThumbsDown, ChevronDown, ChevronUp, ShieldCheck, AlertCircle, ShieldAlert } from "lucide-react";

export function MessageBubble({ message }: { message: Message }) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  const { giveFeedback } = useChatStore();
  const [showTimetable, setShowTimetable] = useState(Boolean(message.metadata?.timetable));
  const [citationStatus, setCitationStatus] = useState("");

  const confidence = message.metadata?.rag_confidence;
  const score = message.metadata?.rag_score;

  const handleFeedback = (val: number) => {
    if (message.id) {
      giveFeedback(message.id, val);
    }
  };

  useEffect(() => {
    if (message.metadata?.timetable) setShowTimetable(true);
  }, [message.metadata?.timetable]);

  return (
    <div className={`group flex flex-col gap-1.5 ${isUser ? "items-end" : "items-start"} mb-4`}>
      <div className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} animate-in fade-in slide-in-from-bottom-2 duration-300 w-full`}>
        <div className={`
          w-8 h-8 rounded-xl flex items-center justify-center shrink-0 mt-0.5 shadow-sm border
          ${isUser 
            ? "bg-ensa-navy text-white border-ensa-navy/10" 
            : "bg-white dark:bg-card text-ensa-blue border-ensa-blue/10 dark:border-ensa-blue/20"}
        `}>
          {isUser ? <User size={16} /> : <Bot size={16} />}
        </div>

        <div className={`
          relative max-w-[85%] px-4 py-3 shadow-md transition-all border
          ${isUser 
            ? "bg-ensa-navy text-white rounded-2xl rounded-tr-none border-ensa-navy/10" 
            : "bg-card text-foreground rounded-2xl rounded-tl-none border-border group-hover:border-ensa-blue/20"}
        `}>
          <div className="flex items-center justify-between gap-1.5 mb-1.5 opacity-40">
            <div className="flex items-center gap-1.5">
              <span className="text-[8px] font-bold uppercase tracking-widest">
                {isUser ? t("common.user_label") : t("common.assistant_name")}
              </span>
              {!isUser && <Sparkles size={8} className="text-ensa-blue" />}
            </div>

            {!isUser && confidence && (
              <div 
                className={`flex items-center gap-1 text-[8px] font-black uppercase tracking-tighter ${
                  confidence === "high" ? "text-ensa-emerald" : confidence === "medium" ? "text-ensa-orange" : "text-destructive"
                }`}
                title={`Confidence: ${confidence} (Score: ${score})`}
                aria-label={`Confidence: ${confidence}`}
              >
                {confidence === "high" ? <ShieldCheck size={10} /> : confidence === "medium" ? <AlertCircle size={10} /> : <ShieldAlert size={10} />}
              </div>
            )}
          </div>

          {message.metadata?.timetable && (
            <div className="mb-3 rounded-xl border border-border/70 bg-muted/20 p-2.5">
              <button
                type="button"
                onClick={() => setShowTimetable((prev) => !prev)}
                className="flex w-full items-center justify-between rounded-lg border border-border bg-card px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-foreground transition-all hover:bg-muted"
              >
                <span>{showTimetable ? t("chat.hide_schedule", { defaultValue: "Masquer l'emploi du temps" }) : t("chat.show_schedule", { defaultValue: "Afficher l'emploi du temps" })}</span>
                {showTimetable ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
              {showTimetable && (
                <div className="mt-2 animate-in fade-in zoom-in-95 duration-300 overflow-hidden">
                  <TimetableGrid timetable={message.metadata.timetable} compact={true} allowDownloadInCompact={true} />
                </div>
              )}
            </div>
          )}

          <div className={`prose prose-sm ${isUser ? "prose-invert" : "dark:prose-invert"} max-w-none prose-p:leading-relaxed prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-pre:rounded-lg`}>
            <ReactMarkdown
              components={{
                img: ({ alt }) => <span>[{alt || "image"}]</span>,
                a: ({ href, children }) => href && /^https?:\/\//i.test(href)
                  ? <a href={href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{children}</a>
                  : <span>{children}</span>,
                h1: ({ children }) => <h1 className="mb-2 text-base font-black uppercase tracking-wider text-ensa-navy dark:text-blue-100">{children}</h1>,
                h2: ({ children }) => <h2 className="mb-2 text-[15px] font-black text-ensa-navy dark:text-blue-100">{children}</h2>,
                h3: ({ children }) => <h3 className="mb-1.5 text-[14px] font-bold text-ensa-blue dark:text-blue-300">{children}</h3>,
                h4: ({ children }) => <h4 className="mb-1.5 text-[13px] font-bold text-foreground">{children}</h4>,
                p: ({ children }) => <p className="mb-2 last:mb-0 text-[14px] font-medium">{children}</p>,
                ul: ({ children }) => <ul className="list-disc ml-4 mb-2 space-y-0.5">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal ml-4 mb-2 space-y-0.5">{children}</ol>,
                li: ({ children }) => <li className="text-[13.5px]">{children}</li>,
                code: ({ children }) => <code className="bg-ensa-blue/10 dark:bg-ensa-blue/20 text-ensa-blue dark:text-blue-300 px-1 py-0.5 rounded font-mono text-[11px] border border-ensa-blue/10">{children}</code>,
                strong: ({ children }) => <strong className="font-extrabold text-ensa-blue dark:text-blue-300">{children}</strong>,
                blockquote: ({ children }) => <blockquote className="my-2 rounded-xl border-l-4 border-ensa-blue bg-ensa-blue/5 px-3 py-2 text-[13px] text-foreground">{children}</blockquote>,
                hr: () => <hr className="my-3 border-border/70" />,
              }}
            >
              {message.content}
            </ReactMarkdown>
            {message.metadata?.security && <div className="mt-3 border-t pt-2 text-sm" aria-live="polite">
              <span>{t(`security.${message.metadata.security.status}`)}</span>
              {message.metadata.security.citations.map((citation, index) => <button
                key={citation.chunk_id} className="ml-2 underline" onClick={async () => {
                  try { await verifySecurityCitation(citation.token); setCitationStatus(t("security.verified")); }
                  catch { setCitationStatus(t("security.source_unavailable")); }
                }}>{t("security.source")} {index + 1}</button>)}
              <span className="block">{citationStatus}</span>
            </div>}
          </div>
          {/* Tail */}
          <div className={`
            absolute top-0 w-3 h-3 
            ${isUser ? "-right-1 bg-ensa-navy border-r border-t border-ensa-navy/10" : "-left-1 bg-card border-l border-t border-border group-hover:border-ensa-blue/20"}
            rotate-45 -z-10 transition-all
          `} />
        </div>
      </div>

      {!isUser && !message.metadata?.security && (
        <div className={`flex gap-1.5 ml-11 mt-0.5 transition-opacity duration-200 ${message.feedback !== 0 ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}>
          <button 
            onClick={() => handleFeedback(1)}
            title={t("chat.useful")}
            className={`p-1 rounded-md border transition-all hover:scale-110 active:scale-95 ${message.feedback === 1 ? "bg-ensa-blue/10 border-ensa-blue text-ensa-blue shadow-sm" : "hover:bg-muted border-transparent text-muted-foreground"}`}
          >
            <ThumbsUp size={12} fill={message.feedback === 1 ? "currentColor" : "none"} strokeWidth={message.feedback === 1 ? 2.5 : 2} />
          </button>
          <button 
            onClick={() => handleFeedback(-1)}
            title={t("chat.not_useful")}
            className={`p-1 rounded-md border transition-all hover:scale-110 active:scale-95 ${message.feedback === -1 ? "bg-red-500/10 border-red-500 text-red-500 shadow-sm" : "hover:bg-muted border-transparent text-muted-foreground"}`}
          >
            <ThumbsDown size={12} fill={message.feedback === -1 ? "currentColor" : "none"} strokeWidth={message.feedback === -1 ? 2.5 : 2} />
          </button>
        </div>
      )}
    </div>
  );
}
