"use client";

import { useEffect, useRef, useState } from "react";
import { toPng } from "html-to-image";
import { toast } from "sonner";
import { Calendar, Clock, Download, MapPin, User as UserIcon, Columns3, Rows3 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Timetable, TimetableSlot } from "@/types";
import { TIMETABLE_DAYS, formatClassLabel, normalizeTimeDisplay, sortTimetableSlots } from "@/lib/timetable";

interface CompactMergedSlot {
  id: string;
  start_time: string;
  end_time: string;
  timeRanges: Array<{ start_time: string; end_time: string }>;
  subject: string;
  professor?: string;
  room?: string;
  type?: string;
  pauses: Array<{ start_time: string; end_time: string; minutes: number }>;
}

interface TimetableGridProps {
  timetable: Timetable;
  compact?: boolean;
  layout?: "columns" | "rows";
  showLayoutToggle?: boolean;
  layoutStorageKey?: string;
  allowDownloadInCompact?: boolean;
}

function getSlotTone(slot: { type?: string }): string {
  const type = (slot.type || "").toLowerCase();
  if (type === "tp") return "bg-ensa-orange/5 border-ensa-orange/20";
  if (type === "td") return "bg-ensa-emerald/5 border-ensa-emerald/20";
  return "bg-ensa-blue/5 border-ensa-blue/10";
}

function toMinutes(value?: string): number | null {
  if (!value) return null;
  const match = value.match(/(\d{1,2}):(\d{2})/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (Number.isNaN(hour) || Number.isNaN(minute)) return null;
  return hour * 60 + minute;
}

function sameCourseIdentity(a: TimetableSlot, b: TimetableSlot): boolean {
  return (
    (a.subject || "").trim().toLowerCase() === (b.subject || "").trim().toLowerCase() &&
    (a.professor || "").trim().toLowerCase() === (b.professor || "").trim().toLowerCase() &&
    (a.room || "").trim().toLowerCase() === (b.room || "").trim().toLowerCase() &&
    (a.type || "").trim().toLowerCase() === (b.type || "").trim().toLowerCase()
  );
}

function mergeSlotsForCompactView(slots: TimetableSlot[], maxGapMinutes = 20): CompactMergedSlot[] {
  const merged: CompactMergedSlot[] = [];

  for (const slot of slots) {
    const previous = merged[merged.length - 1];
    if (!previous) {
      merged.push({
        id: String(slot.id),
        start_time: slot.start_time,
        end_time: slot.end_time,
        timeRanges: [{ start_time: slot.start_time, end_time: slot.end_time }],
        subject: slot.subject,
        professor: slot.professor,
        room: slot.room,
        type: slot.type,
        pauses: [],
      });
      continue;
    }

    const previousAsSlot = {
      id: 0,
      timetable_id: 0,
      day_of_week: 0,
      start_time: previous.start_time,
      end_time: previous.end_time,
      subject: previous.subject,
      professor: previous.professor,
      room: previous.room,
      type: previous.type,
    } as TimetableSlot;

    const prevEnd = toMinutes(previous.end_time);
    const nextStart = toMinutes(slot.start_time);
    const gap = prevEnd !== null && nextStart !== null ? nextStart - prevEnd : null;

    if (sameCourseIdentity(previousAsSlot, slot) && gap !== null && gap >= 0 && gap <= maxGapMinutes) {
      if (gap > 0) {
        previous.pauses.push({
          start_time: previous.end_time,
          end_time: slot.start_time,
          minutes: gap,
        });
      }
      previous.timeRanges.push({ start_time: slot.start_time, end_time: slot.end_time });
      previous.end_time = slot.end_time;
      previous.id = `${previous.id}-${slot.id}`;
      continue;
    }

    merged.push({
      id: String(slot.id),
      start_time: slot.start_time,
      end_time: slot.end_time,
      timeRanges: [{ start_time: slot.start_time, end_time: slot.end_time }],
      subject: slot.subject,
      professor: slot.professor,
      room: slot.room,
      type: slot.type,
      pauses: [],
    });
  }

  return merged;
}

function extractFiliereLabel(classLabel: string): string {
  const normalized = classLabel.replace(/[_-]+/g, " ").trim();
  const first = normalized.split(/\s+/)[0] || classLabel;
  return first.toUpperCase();
}

export function TimetableGrid({
  timetable,
  compact = false,
  layout = "columns",
  showLayoutToggle = false,
  layoutStorageKey = "usms_timetable_layout",
  allowDownloadInCompact = false
}: TimetableGridProps) {
  const { t } = useTranslation();
  const gridRef = useRef<HTMLDivElement>(null);
  const [activeLayout, setActiveLayout] = useState<"columns" | "rows">(layout);
  const sortedSlots = sortTimetableSlots(timetable.slots || []);
  const filiereLabel = extractFiliereLabel(timetable.class_label);

  useEffect(() => {
    setActiveLayout(layout);
  }, [layout]);

  useEffect(() => {
    if (!showLayoutToggle) return;
    try {
      const saved = window.localStorage.getItem(layoutStorageKey);
      if (saved === "columns" || saved === "rows") {
        setActiveLayout(saved);
      }
    } catch {
      // Ignore persistence errors in restricted environments.
    }
  }, [showLayoutToggle, layoutStorageKey]);

  useEffect(() => {
    if (!showLayoutToggle) return;
    try {
      window.localStorage.setItem(layoutStorageKey, activeLayout);
    } catch {
      // Ignore persistence errors in restricted environments.
    }
  }, [showLayoutToggle, layoutStorageKey, activeLayout]);

  const slotsByDay = TIMETABLE_DAYS.map((day, dayIdx) => ({
    day,
    slots: sortedSlots.filter((slot) => slot.day_of_week === dayIdx),
  }));

  const compactSlotsByDay = slotsByDay.map(({ day, slots }) => ({
    day,
    slots: mergeSlotsForCompactView(slots),
  }));

  const filledDays = slotsByDay.filter(({ slots }) => slots.length > 0);
  const totalCourses = sortedSlots.length;
  const canDownload = !compact || allowDownloadInCompact;

  const downloadImage = async () => {
    if (!gridRef.current) return;
    try {
      const dataUrl = await toPng(gridRef.current, { cacheBust: true, backgroundColor: "white" });
      const link = document.createElement("a");
      link.download = `EDT_${timetable.class_label}.png`;
      link.href = dataUrl;
      link.click();
      toast.success(t("common.download_success", { defaultValue: "Image téléchargée" }));
    } catch {
      toast.error(t("common.download_error", { defaultValue: "Erreur de téléchargement" }));
    }
  };

  return (
    <div className="space-y-4 w-full">
      <div className="flex flex-col gap-3 px-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-ensa-blue/10 text-ensa-blue">
            <Calendar size={18} />
          </div>
          <div>
            <h3 className="font-poppins text-sm font-bold uppercase tracking-widest text-ensa-navy dark:text-blue-100">
              Filiere {filiereLabel}
            </h3>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              {formatClassLabel(timetable.class_label)} · {timetable.semester} · {timetable.academic_year} · {totalCourses} {totalCourses > 1 ? "séances" : "séance"}
            </p>
          </div>
        </div>
        {canDownload && (
          <div className="flex flex-wrap items-center justify-end gap-2">
            {!compact && showLayoutToggle && (
              <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1">
                <button
                  type="button"
                  onClick={() => setActiveLayout("rows")}
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[9px] font-bold uppercase tracking-widest transition-all ${
                    activeLayout === "rows"
                      ? "bg-ensa-blue text-white"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                  title={t("admin.horizontal", { defaultValue: "Horizontal" })}
                >
                  <Rows3 size={11} />
                  H
                </button>
                <button
                  type="button"
                  onClick={() => setActiveLayout("columns")}
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[9px] font-bold uppercase tracking-widest transition-all ${
                    activeLayout === "columns"
                      ? "bg-ensa-blue text-white"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                  title={t("admin.vertical", { defaultValue: "Vertical" })}
                >
                  <Columns3 size={11} />
                  V
                </button>
              </div>
            )}
            <button
              onClick={downloadImage}
              className={`flex items-center justify-center gap-1.5 rounded-lg bg-ensa-blue/10 text-[10px] font-bold uppercase tracking-widest text-ensa-blue transition-all hover:bg-ensa-blue hover:text-white ${compact ? "px-2.5 py-1.5" : "px-3 py-2"}`}
            >
              <Download size={compact ? 11 : 12} />
              {compact
                ? t("common.download", { defaultValue: "Telecharger" })
                : t("common.save_as_image", { defaultValue: "Sauvegarder l'image" })}
            </button>
          </div>
        )}
      </div>

      <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-lg">
        <div ref={gridRef} className={`bg-white ${compact ? "p-4" : "p-6 sm:p-8"}`}>
          <div className="mb-6 flex items-center justify-between border-b border-ensa-blue/15 pb-4">
            <div>
              <h2 className="text-lg font-poppins font-black uppercase leading-none text-ensa-navy">Emploi du temps</h2>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.3em] text-ensa-blue">ENSA Béni Mellal · USMS</p>
            </div>
            <div className="text-right">
              <p className="text-[10px] font-black uppercase tracking-tight text-ensa-blue">Filiere {filiereLabel}</p>
              <p className="text-[10px] font-black uppercase tracking-tight text-ensa-navy">{timetable.academic_year}</p>
              <p className="text-[10px] font-bold uppercase text-muted-foreground">{timetable.semester}</p>
            </div>
          </div>

          {compact ? (
            <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
              {compactSlotsByDay.some(({ slots }) => slots.length > 0) ? (
                compactSlotsByDay.filter(({ slots }) => slots.length > 0).map(({ day, slots }) => (
                  <section key={day} className="rounded-2xl border border-border bg-slate-50 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <h4 className="text-[11px] font-black uppercase tracking-[0.18em] text-ensa-navy">{day}</h4>
                      <span className="rounded-full bg-ensa-blue/10 px-2 py-1 text-[9px] font-bold uppercase tracking-widest text-ensa-blue">
                        {slots.length} {slots.length > 1 ? "blocs" : "bloc"}
                      </span>
                    </div>
                    <div className="space-y-1.5">
                      {slots.map((slot) => (
                        <div key={slot.id} className={`rounded-xl border p-2.5 shadow-sm ${getSlotTone(slot)}`}>
                          <div className="mb-1.5 flex items-center gap-1.5 text-ensa-navy/70">
                            <Clock size={11} className="shrink-0" />
                            <div className="flex flex-wrap items-center gap-1.5">
                              {slot.timeRanges.map((range, idx) => (
                                <span
                                  key={`${slot.id}-range-${idx}`}
                                  className="rounded-md border border-ensa-blue/25 bg-white/80 px-1.5 py-0.5 text-[9px] font-black tracking-wide text-ensa-navy"
                                >
                                  {normalizeTimeDisplay(range.start_time)} - {normalizeTimeDisplay(range.end_time)}
                                </span>
                              ))}
                            </div>
                          </div>

                          {slot.pauses.length > 0 && (
                            <div className="mb-1.5 flex flex-wrap gap-1 text-[8px] font-black uppercase tracking-widest text-ensa-orange">
                              {slot.pauses.map((pause, idx) => (
                                <span key={`${slot.id}-pause-${idx}`} className="rounded-full bg-ensa-orange/15 px-1.5 py-0.5">
                                  Pause {normalizeTimeDisplay(pause.start_time)} - {normalizeTimeDisplay(pause.end_time)} ({pause.minutes} min)
                                </span>
                              ))}
                            </div>
                          )}

                          <p className="text-[11px] font-black uppercase tracking-tight text-ensa-navy">{slot.subject}</p>
                          <div className="mt-1.5 flex flex-wrap gap-2 text-[9px] font-medium text-muted-foreground">
                            {slot.professor && (
                              <span className="inline-flex items-center gap-1">
                                <UserIcon size={10} />
                                {slot.professor}
                              </span>
                            )}
                            {slot.room && (
                              <span className="inline-flex items-center gap-1 text-ensa-blue">
                                <MapPin size={10} />
                                {slot.room}
                              </span>
                            )}
                            {slot.type && (
                              <span className="rounded-full bg-ensa-navy px-1.5 py-0.5 text-[8px] font-black uppercase tracking-widest text-white">
                                {slot.type}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                ))
              ) : (
                <div className="rounded-2xl border-2 border-dashed border-border p-6 text-center text-xs font-bold uppercase tracking-widest text-muted-foreground">
                  {t("common.empty_day", { defaultValue: "Aucun cours programmé" })}
                </div>
              )}
            </div>
          ) : activeLayout === "rows" ? (
            <div className="space-y-3">
              {slotsByDay.map(({ day, slots }) => (
                <section key={day} className="rounded-xl border border-border bg-slate-50 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <h4 className="text-[10px] font-black uppercase tracking-[0.18em] text-ensa-navy">{day}</h4>
                    <span className="rounded-full bg-ensa-blue/10 px-2 py-1 text-[9px] font-bold uppercase tracking-widest text-ensa-blue">
                      {slots.length} {slots.length > 1 ? "cours" : "cours"}
                    </span>
                  </div>

                  {slots.length > 0 ? (
                    <div className="overflow-x-auto">
                      <div className="flex min-w-max gap-2 pr-1">
                        {slots.map((slot) => (
                          <div key={slot.id} className={`w-64 shrink-0 rounded-xl border p-3 shadow-sm ${getSlotTone(slot)}`}>
                            <div className="mb-1.5 flex items-center gap-1 text-ensa-navy/70">
                              <Clock size={10} />
                              <span className="text-[10px] font-bold">
                                {normalizeTimeDisplay(slot.start_time)} - {normalizeTimeDisplay(slot.end_time)}
                              </span>
                            </div>

                            <p className="mb-2 text-[11px] font-black uppercase leading-tight tracking-tight text-ensa-navy">
                              {slot.subject}
                            </p>

                            <div className="space-y-1">
                              {slot.professor && (
                                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                                  <UserIcon size={9} className="shrink-0" />
                                  <span className="truncate font-medium">{slot.professor}</span>
                                </div>
                              )}
                              {slot.room && (
                                <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-ensa-blue">
                                  <MapPin size={9} className="shrink-0" />
                                  <span>{slot.room}</span>
                                </div>
                              )}
                              {slot.type && (
                                <div className="pt-1">
                                  <span className="rounded px-1.5 py-0.5 text-[8px] font-black uppercase tracking-widest text-white bg-ensa-navy">
                                    {slot.type}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-lg border-2 border-dashed border-border/60 py-3 text-center text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                      Aucun cours
                    </div>
                  )}
                </section>
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <div className="grid min-w-[900px] grid-cols-6 gap-3">
                {slotsByDay.map(({ day, slots }) => (
                  <div key={day} className="space-y-3">
                    <div className="rounded-lg bg-ensa-navy py-2 text-center shadow-md">
                      <span className="text-[10px] font-black uppercase tracking-widest text-white">{day}</span>
                    </div>

                    <div className="min-h-[320px] space-y-2">
                      {slots.length > 0 ? (
                        slots.map((slot) => (
                          <div key={slot.id} className={`rounded-xl border p-3 shadow-sm ${getSlotTone(slot)}`}>
                            <div className="mb-1.5 flex items-center gap-1 text-ensa-navy/70">
                              <Clock size={10} />
                              <span className="text-[10px] font-bold">
                                {normalizeTimeDisplay(slot.start_time)} - {normalizeTimeDisplay(slot.end_time)}
                              </span>
                            </div>

                            <p className="mb-2 text-[11px] font-black uppercase leading-tight tracking-tight text-ensa-navy">
                              {slot.subject}
                            </p>

                            <div className="space-y-1">
                              {slot.professor && (
                                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                                  <UserIcon size={9} className="shrink-0" />
                                  <span className="truncate font-medium">{slot.professor}</span>
                                </div>
                              )}
                              {slot.room && (
                                <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-ensa-blue">
                                  <MapPin size={9} className="shrink-0" />
                                  <span>{slot.room}</span>
                                </div>
                              )}
                              {slot.type && (
                                <div className="pt-1">
                                  <span className="rounded px-1.5 py-0.5 text-[8px] font-black uppercase tracking-widest text-white bg-ensa-navy">
                                    {slot.type}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="flex h-full items-center justify-center rounded-xl border-2 border-dashed border-border/50 opacity-30">
                          <span className="rotate-90 whitespace-nowrap text-[9px] font-bold uppercase tracking-widest">Aucun cours</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mt-6 flex items-center justify-between border-t border-border pt-4 opacity-50">
            <p className="text-[8px] font-bold uppercase text-ensa-navy">Généré par Chatbot USMS</p>
            <p className="text-[8px] font-medium text-ensa-navy">{new Date().toLocaleString()}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
