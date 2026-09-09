"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { publishTimetable } from "@/lib/api";
import { useTranslation } from "react-i18next";
import type { Jour, Timetable } from "@/types";
import { buildDraftTimetable } from "@/lib/timetable";
import { TimetableGrid } from "@/components/chat/TimetableGrid";
import { Plus, Trash2, Eye, Send, Calendar, Clock, User, MapPin, Layers, X } from "lucide-react";

const JOURS: Jour[] = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];
const FILIERES = ["IACS", "TDI", "G2ER", "IAA", "2AP"] as const;
const SEMESTRES = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"] as const;

const CRENEAUX = {
  normale: ["08h30->10h00", "10h15->11h45", "13h00->14h30", "14h45->16h15"],
  ramadan: ["09h00->10h30", "10h45->12h15", "12h45->14h15", "14h30->16h00"],
  vendredi: ["13h30->15h00", "15h15->16h45"]
};

const schema = z.object({
  filiere: z.enum(FILIERES),
  semestre: z.enum(SEMESTRES),
  annee: z.string().regex(/^\d{4}-\d{4}$/),
  periode: z.enum(["normale", "ramadan"]),
  salle: z.string().min(1)
});

type FormData = z.infer<typeof schema>;

interface EdtFormProps {
  onUploaded?: () => void | Promise<void>;
  initialTimetableTemplate?: Timetable | null;
}

interface CreneauUI {
  debut: string;
  fin: string;
  contenu: string;
  professeur: string;
  salle: string;
  seance?: string;
}

function blankCreneau(defaultHour: string): CreneauUI {
  const parts = defaultHour.split("->").map((part) => part.trim());
  return { debut: parts[0] || "09h00", fin: parts[1] || "10h30", contenu: "", professeur: "", salle: "", seance: "" };
}

function formatTimeForInput(value: string): string {
  const parts = value.split(":");
  if (parts.length >= 2) {
    return `${parts[0]}h${parts[1]}`;
  }
  return value.replace(":", "h");
}

export function EdtForm({ onUploaded, initialTimetableTemplate }: EdtFormProps) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Record<Jour, CreneauUI[]>>({
    Lundi: [],
    Mardi: [],
    Mercredi: [],
    Jeudi: [],
    Vendredi: [],
    Samedi: []
  });
  const [showVisualPreview, setShowVisualPreview] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const form = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      filiere: "IACS",
      semestre: "S4",
      annee: "2025-2026",
      periode: "normale",
      salle: "A01"
    }
  });

  useEffect(() => {
    if (!initialTimetableTemplate) return;

    const filiereFromLabel = initialTimetableTemplate.class_label.split("_")[0] || "";
    const filiere = FILIERES.includes(filiereFromLabel as FormData["filiere"])
      ? (filiereFromLabel as FormData["filiere"])
      : form.getValues("filiere");

    const semestre = SEMESTRES.includes(initialTimetableTemplate.semester as FormData["semestre"])
      ? (initialTimetableTemplate.semester as FormData["semestre"])
      : form.getValues("semestre");

    const annee = /^\d{4}-\d{4}$/.test(initialTimetableTemplate.academic_year)
      ? initialTimetableTemplate.academic_year
      : form.getValues("annee");

    const salleParDefaut =
      initialTimetableTemplate.slots.find((slot) => Boolean(slot.room?.trim()))?.room?.trim() ||
      form.getValues("salle");

    form.reset({
      filiere,
      semestre,
      annee,
      periode: form.getValues("periode"),
      salle: salleParDefaut,
    });

    const nextRows: Record<Jour, CreneauUI[]> = {
      Lundi: [],
      Mardi: [],
      Mercredi: [],
      Jeudi: [],
      Vendredi: [],
      Samedi: []
    };

    const sortedSlots = [...initialTimetableTemplate.slots].sort((a, b) => {
      if (a.day_of_week !== b.day_of_week) return a.day_of_week - b.day_of_week;
      return a.start_time.localeCompare(b.start_time);
    });

    for (const slot of sortedSlots) {
      const day = JOURS[slot.day_of_week];
      if (!day) continue;
      nextRows[day].push({
        debut: formatTimeForInput(slot.start_time),
        fin: formatTimeForInput(slot.end_time),
        contenu: slot.subject || "",
        professeur: slot.professor || "",
        salle: slot.room || salleParDefaut,
        seance: slot.type || "Cours",
      });
    }

    setRows(nextRows);
    setShowVisualPreview(true);
  }, [initialTimetableTemplate, form]);

  const clearDay = useCallback((day: Jour) => {
    setRows(state => ({ ...state, [day]: [] }));
  }, []);

  const periode = form.watch("periode");

  const hoursForDay = useMemo(() => {
    return (day: Jour) => {
      if (day === "Vendredi") return CRENEAUX.vendredi;
      return periode === "ramadan" ? CRENEAUX.ramadan : CRENEAUX.normale;
    };
  }, [periode]);

  const draftTimetable = useMemo(() => buildDraftTimetable({
    classLabel: `${form.watch("filiere")}_${form.watch("annee")}_${form.watch("semestre")}`,
    academicYear: form.watch("annee"),
    semester: form.watch("semestre"),
    rows,
  }), [form, rows]);

  const addRow = useCallback((day: Jour) => {
    const first = hoursForDay(day)[0] ?? "08h30->10h00";
    setRows((state) => ({ ...state, [day]: [...state[day], blankCreneau(first)] }));
  }, [hoursForDay]);

  const removeRow = useCallback((day: Jour, idx: number) => {
    setRows((state) => ({ ...state, [day]: state[day].filter((_, i) => i !== idx) }));
  }, []);

  const updateRow = useCallback((day: Jour, idx: number, key: keyof CreneauUI, value: string) => {
    setRows((state) => ({
      ...state,
      [day]: state[day].map((r, i) => (i === idx ? { ...r, [key]: value } : r))
    }));
  }, []);

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      setSubmitting(true);
      const timetableToPublish = buildDraftTimetable({
        classLabel: `${values.filiere}_${values.annee}_${values.semestre}`,
        academicYear: values.annee,
        semester: values.semestre,
        rows,
      });

      // Validation : vérifier qu'il y a au moins un créneau
      if (timetableToPublish.slots.length === 0) {
        toast.error("L'emploi du temps doit contenir au moins un créneau");
        return;
      }

      // Validation : limiter le nombre de créneaux pour éviter les payloads trop gros
      if (timetableToPublish.slots.length > 200) {
        toast.error("Trop de créneaux (maximum 200)");
        return;
      }

      await publishTimetable({
        class_label: timetableToPublish.class_label,
        academic_year: values.annee,
        semester: values.semestre,
        slots: timetableToPublish.slots.map((slot) => ({
          day_of_week: slot.day_of_week,
          start_time: slot.start_time,
          end_time: slot.end_time,
          subject: slot.subject,
          professor: slot.professor || "",
          room: slot.room || values.salle,
          type: slot.type || "Cours",
        }))
      });

      toast.success("Emploi du temps publié en base de données");
      if (onUploaded) {
        await onUploaded();
      }
    } catch (error) {
      console.error(error);
      toast.error("Échec de l'envoi de l'EDT");
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <div className="space-y-6 font-inter">
      <div className="p-3 bg-ensa-blue/5 border border-ensa-blue/10 rounded-xl flex items-start gap-2.5">
        <Plus size={16} className="text-ensa-blue mt-0.5" />
        <p className="text-[11px] font-medium text-ensa-navy dark:text-blue-200 leading-relaxed">
          {t("admin.manual_config")}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="space-y-1">
          <label className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground ml-1">{t("common.filiere")}</label>
          <select className="w-full bg-muted/50 border border-border rounded-lg px-2.5 py-2 text-xs font-semibold outline-none focus:border-ensa-blue transition-all" {...form.register("filiere")}>
            {FILIERES.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground ml-1">{t("admin.academic_year", { defaultValue: "Année universitaire" })}</label>
          <input
            className="w-full bg-muted/50 border border-border rounded-lg px-2.5 py-2 text-xs font-semibold outline-none focus:border-ensa-blue transition-all"
            placeholder="2025-2026"
            {...form.register("annee")}
          />
        </div>
        <div className="space-y-1">
          <label className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground ml-1">{t("admin.semestre", { defaultValue: "Semestre" })}</label>
          <select className="w-full bg-muted/50 border border-border rounded-lg px-2.5 py-2 text-xs font-semibold outline-none focus:border-ensa-blue transition-all" {...form.register("semestre")}>
            {SEMESTRES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground ml-1">{t("admin.default_room")}</label>
          <input className="w-full bg-muted/50 border border-border rounded-lg px-2.5 py-2 text-xs font-semibold outline-none focus:border-ensa-blue transition-all" placeholder="A13" {...form.register("salle")} />
        </div>
      </div>

      <div className="flex items-center justify-between p-3 bg-muted/30 border border-border rounded-xl">
        <div className="flex items-center gap-2">
          <Layers size={16} className="text-muted-foreground" />
          <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
            {t("admin.total_slots", { defaultValue: "Créneaux totaux" })}: {draftTimetable.slots.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Eye size={16} className="text-muted-foreground" />
          <button
            type="button"
            onClick={() => setShowVisualPreview(!showVisualPreview)}
            className="text-xs font-bold uppercase tracking-widest text-ensa-blue hover:text-ensa-navy transition-all"
          >
            {showVisualPreview ? t("admin.hide_preview") : t("admin.preview_image")}
          </button>
        </div>
      </div>

      {showVisualPreview && (
        <div className="bg-card border border-border rounded-xl p-4">
          <TimetableGrid timetable={draftTimetable} />
        </div>
      )}

      <div className="space-y-4">
        {JOURS.map((day) => (
          <div key={day} className="bg-card border border-border rounded-xl overflow-hidden transition-all hover:border-ensa-blue/20">
            <div className="px-4 py-3 bg-muted/30 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Calendar size={16} className="text-ensa-navy dark:text-blue-200" />
                <h3 className="font-poppins font-bold uppercase tracking-widest text-ensa-navy dark:text-blue-100 text-xs">{day}</h3>
              </div>
              <div className="flex items-center gap-1.5">
                <button 
                  type="button" 
                  onClick={() => addRow(day)} 
                  className="flex items-center gap-1.5 bg-ensa-blue text-white px-3 py-1.5 rounded-lg text-[9px] font-bold uppercase tracking-widest hover:bg-ensa-navy transition-all shadow-sm"
                >
                  <Plus size={12} /> {t("admin.add_course")}
                </button>

                {rows[day].length > 0 && (
                  <button 
                    type="button" 
                    onClick={() => clearDay(day)} 
                    className="p-1.5 text-muted-foreground hover:text-destructive transition-all"
                    title="Vider ce jour"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
            </div>

            <div className="p-3 space-y-2">
              {rows[day].length === 0 ? (
                <p className="text-[9px] font-bold uppercase text-muted-foreground/40 text-center py-2 tracking-widest">{t("admin.empty_day")}</p>
              ) : (
                rows[day].map((row, idx) => (
                  <div key={`${day}-${idx}`} className="grid grid-cols-1 md:grid-cols-12 gap-2 p-3 bg-muted/20 rounded-xl border border-border group relative">
                    <div className="md:col-span-3 space-y-0.5">
                      <div className="flex items-center gap-1 ml-1 text-muted-foreground">
                        <Clock size={9} /> <span className="text-[8px] font-bold uppercase tracking-tighter">{t("admin.hour")}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <input
                          type="text"
                          className="w-full bg-card border border-border rounded-lg px-2 py-1.5 text-xs font-bold outline-none focus:border-ensa-blue"
                          value={row.debut}
                          onChange={(e) => updateRow(day, idx, "debut", e.target.value)}
                          placeholder="Début"
                        />
                        <span className="text-muted-foreground text-[10px]">{t("common.to")}</span>
                        <input
                          type="text"
                          className="w-full bg-card border border-border rounded-lg px-2 py-1.5 text-xs font-bold outline-none focus:border-ensa-blue"
                          value={row.fin}
                          onChange={(e) => updateRow(day, idx, "fin", e.target.value)}
                          placeholder="Fin"
                        />
                      </div>
                    </div>
                    
                    <div className="md:col-span-3 space-y-0.5">
                      <div className="flex items-center gap-1 ml-1 text-muted-foreground">
                        <Layers size={9} /> <span className="text-[8px] font-bold uppercase tracking-tighter">{t("admin.subject")}</span>
                      </div>
                      <input className="w-full bg-card border border-border rounded-lg px-2.5 py-1.5 text-xs font-bold outline-none focus:border-ensa-blue" placeholder="Ex: Analyse" value={row.contenu} onChange={(e) => updateRow(day, idx, "contenu", e.target.value)} />
                    </div>

                    <div className="md:col-span-3 space-y-0.5">
                      <div className="flex items-center gap-1 ml-1 text-muted-foreground">
                        <User size={9} /> <span className="text-[8px] font-bold uppercase tracking-tighter">{t("admin.professor")}</span>
                      </div>
                      <input className="w-full bg-card border border-border rounded-lg px-2.5 py-1.5 text-xs font-bold outline-none focus:border-ensa-blue" placeholder="Enseignant" value={row.professeur} onChange={(e) => updateRow(day, idx, "professeur", e.target.value)} />
                    </div>

                    <div className="md:col-span-2 space-y-0.5">
                      <div className="flex items-center gap-1 ml-1 text-muted-foreground">
                        <MapPin size={9} /> <span className="text-[8px] font-bold uppercase tracking-tighter">{t("admin.room")}</span>
                      </div>
                      <input className="w-full bg-card border border-border rounded-lg px-2.5 py-1.5 text-xs font-bold outline-none focus:border-ensa-blue" placeholder="A13" value={row.salle} onChange={(e) => updateRow(day, idx, "salle", e.target.value)} />
                    </div>

                    <div className="md:col-span-1 flex items-end pb-0.5">
                      <button type="button" onClick={() => removeRow(day, idx)} className="w-full flex items-center justify-center p-1.5 rounded-lg text-destructive hover:bg-destructive/10 transition-all border border-transparent hover:border-destructive/20">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-3 pt-4 border-t border-border">
        <button 
          type="button" 
          onClick={() => setShowVisualPreview((prev) => !prev)}
          disabled={submitting} 
          className="flex items-center gap-1.5 px-4 py-2.5 border border-border rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-muted transition-all disabled:opacity-50"
        >
          <Eye size={16} /> {showVisualPreview ? t("admin.hide_preview", { defaultValue: "Masquer l'aperçu" }) : t("admin.preview_image", { defaultValue: "Prévisualiser l'image" })}
        </button>
        <button 
          type="button" 
          onClick={onSubmit} 
          disabled={submitting} 
          className="flex items-center gap-1.5 px-6 py-2.5 bg-ensa-blue text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-ensa-navy transition-all disabled:opacity-50 shadow-md"
        >
          {submitting ? <Clock className="animate-spin" size={16} /> : <Send size={16} />}
          {submitting ? "..." : t("admin.publish_edt")}
        </button>
      </div>

      {showVisualPreview && draftTimetable.slots.length > 0 && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between px-1">
            <p className="text-[9px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
              {t("admin.preview_image", { defaultValue: "Prévisualisation image" })}
            </p>
            <p className="text-[9px] font-bold uppercase tracking-widest text-ensa-blue">
              Aperçu avant publication
            </p>
          </div>
          <TimetableGrid timetable={draftTimetable} layout="rows" showLayoutToggle={true} />
        </div>
      )}

      {submitting && (
        <div className="fixed bottom-6 right-6 z-50 bg-ensa-navy text-white p-4 rounded-2xl shadow-2xl animate-in slide-in-from-right-10">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
            <div>
              <p className="text-xs font-bold uppercase tracking-widest">{t("common.syncing")}</p>
              <p className="text-[9px] opacity-60 font-bold uppercase tracking-tighter">{t("admin.updating_db")}</p>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
