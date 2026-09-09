export type Role = "student" | "admin";

export interface User {
  id: number;
  email: string;
  role: Role;
  class_label: string | null;
  language?: string;
  created_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Conversation {
  id: number;
  user_id: number;
  title: string;
  created_at: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  role: "user" | "assistant";
  content: string;
  source_file?: string | null;
  feedback?: number;
  metadata?: MessageMetadata;
  created_at: string;
}

export interface ChatResponse {
  answer: string;
  conversation_id: number | null;
  class_label: string | null;
  requires_class_selection: boolean;
  available_classes: string[];
  source_file: string | null;
  timetable?: Timetable | null;
  rag_confidence?: string;
  rag_score?: number;
}

export interface MessageMetadata {
  source_files?: string | string[] | null;
  timetable?: Timetable | null;
  type?: string;
  rag_confidence?: string;
  rag_score?: number;
}

export interface StatsResponse {
  total_users: number;
  total_conversations: number;
  total_messages: number;
  top_questions: Array<{ question: string; count: number }>;
  weak_questions: Array<{ question: string; count: number; occurrences?: number; last_seen?: string }>;
  feedback_stats: { positive: number; negative: number };
}

export interface QaPair {
  question: string;
  answer: string;
  feedback?: number;
  email: string;
  created_at: string;
}

export interface UserActivity {
  id: number;
  email: string;
  role: Role;
  class_label: string | null;
  conversations_count: number;
  messages_count: number;
}

export interface FaqFileEntry {
  name: string;
  size_kb: number;
  updated_at: string;
}

export interface EdtFileEntry {
  class_folder: string;
  name: string;
  size_kb: number;
  updated_at: string;
}

export interface PublishedTimetable {
  id: number;
  class_label: string;
  academic_year: string;
  semester: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EdtClassInfo {
  label: string;
  has_calendrier: boolean;
}

export type ClassChangeStatus = "pending" | "approved" | "rejected";

export interface ClassChangeRequest {
  id: number;
  user_id: number;
  user_email?: string;
  current_class_label: string | null;
  requested_class_label: string;
  reason: string | null;
  status: ClassChangeStatus;
  review_note: string | null;
  reviewed_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface Creneau {
  heure: string;
  contenu: string;
  professeur: string;
  salle: string;
  seance?: string;
}

export type Jour = "Lundi" | "Mardi" | "Mercredi" | "Jeudi" | "Vendredi" | "Samedi";

export interface EdtJson {
  filiere: "IACS" | "TDI" | "G2ER" | "IAA" | "2AP";
  niveau: "1" | "2" | "3" | "4" | "5";
  semestre: "S1" | "S2" | "S3" | "S4" | "S5" | "S6" | "S7" | "S8" | "S9" | "S10";
  annee: string;
  periode: "Normale" | "Ramadan";
  salle: string;
  Lundi: Creneau[];
  Mardi: Creneau[];
  Mercredi: Creneau[];
  Jeudi: Creneau[];
  Vendredi: Creneau[];
  Samedi: Creneau[];
}

export interface TimetableSlot {
  id: number;
  timetable_id: number;
  day_of_week: number;
  start_time: string;
  end_time: string;
  subject: string;
  professor?: string;
  room?: string;
  type?: string;
}

export interface Timetable {
  id: number;
  class_label: string;
  academic_year: string;
  semester: string;
  is_active: boolean;
  slots: TimetableSlot[];
  created_at: string;
  updated_at: string;
}

export type RevisionPriority = "low" | "medium" | "high";
export type RevisionDifficulty = "easy" | "medium" | "hard";

export interface RevisionPlanModule {
  id: string;
  name: string;
  exam_date: string;
  priority: RevisionPriority;
  difficulty: RevisionDifficulty;
}

export interface RevisionAvailabilitySlot {
  day: string;
  start_time: string;
  end_time: string;
}

export interface RevisionPlanSession {
  id: string;
  date: string;
  date_label: string;
  session_window: string;
  duration_hours: number;
  module_id: string;
  module_name: string;
  focus: string;
  note?: string | null;
  is_exam_day?: boolean;
}

export interface RevisionPlan {
  id: number;
  user_id: number;
  title: string;
  modules: RevisionPlanModule[];
  availability: RevisionAvailabilitySlot[];
  sessions: RevisionPlanSession[];
  created_at: string;
  updated_at: string;
}
