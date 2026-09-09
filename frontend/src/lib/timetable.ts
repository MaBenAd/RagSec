"use client";

import type { Jour, Timetable, TimetableSlot } from "@/types";

const DAY_INDEX: Record<Jour, number> = {
  Lundi: 0,
  Mardi: 1,
  Mercredi: 2,
  Jeudi: 3,
  Vendredi: 4,
  Samedi: 5,
};

export const TIMETABLE_DAYS: Jour[] = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];

export function dayNameToIndex(day: Jour): number {
  return DAY_INDEX[day];
}

export function formatClassLabel(label: string): string {
  return label
    .replace(/[_-]+/g, " ")
    .replace(/\bY(\d+)\b/gi, "Année $1")
    .replace(/\bS(\d+)\b/gi, "S$1")
    .trim();
}

export function normalizeTimeDisplay(value: string): string {
  const raw = (value || "").trim();
  if (!raw) return "--:--";
  const match = raw.match(/^(\d{1,2})[:hH](\d{2})$/);
  if (match) {
    return `${match[1].padStart(2, "0")}:${match[2]}`;
  }
  return raw.replace(/h/gi, ":");
}

export function slotTimeSortValue(value: string): number {
  const formatted = normalizeTimeDisplay(value);
  const [hours, minutes] = formatted.split(":").map((part) => Number(part));
  if (Number.isNaN(hours) || Number.isNaN(minutes)) return Number.MAX_SAFE_INTEGER;
  return (hours * 60) + minutes;
}

export function sortTimetableSlots(slots: TimetableSlot[]): TimetableSlot[] {
  return [...slots].sort((a, b) => {
    if (a.day_of_week !== b.day_of_week) return a.day_of_week - b.day_of_week;
    return slotTimeSortValue(a.start_time) - slotTimeSortValue(b.start_time);
  });
}

export function buildDraftTimetable(input: {
  classLabel: string;
  academicYear: string;
  semester: string;
  rows: Record<Jour, Array<{
    debut: string;
    fin: string;
    contenu: string;
    professeur: string;
    salle: string;
    seance?: string;
  }>>;
}): Timetable {
  const slots: TimetableSlot[] = [];
  let slotId = 1;

  TIMETABLE_DAYS.forEach((day) => {
    for (const row of input.rows[day] || []) {
      if (!row.contenu.trim()) continue;
      slots.push({
        id: slotId++,
        timetable_id: 0,
        day_of_week: dayNameToIndex(day),
        start_time: normalizeTimeDisplay(row.debut),
        end_time: normalizeTimeDisplay(row.fin),
        subject: row.contenu.trim(),
        professor: row.professeur.trim(),
        room: row.salle.trim(),
        type: (row.seance || "Cours").trim(),
      });
    }
  });

  return {
    id: 0,
    class_label: input.classLabel,
    academic_year: input.academicYear,
    semester: input.semester,
    is_active: false,
    slots: sortTimetableSlots(slots),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}
