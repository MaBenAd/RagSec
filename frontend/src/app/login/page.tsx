"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import axios from "axios";
import { useAuthStore } from "@/store/useAuthStore";
import { useTheme } from "@/components/providers/ThemeProvider";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Moon, Sun, GraduationCap, IdCard, LogIn, ShieldCheck, HelpCircle, Eye, EyeOff, BookOpen } from "lucide-react";
import Modal from "@/components/Modal";
import PrivacyPolicies from "@/components/PrivacyPolicies";

function isUsmsEmail(value: string): boolean {
  const email = value.trim().toLowerCase();
  if (!email.includes("@")) return false;
  const domain = email.split("@").pop();
  return domain === "usms.ac.ma" || domain === "usms.ma";
}

const TRACK_OPTIONS = ["2AP", "IACS", "TDI", "G2ER", "IAA"] as const;

const ENGINEERING_SEMESTERS = [
  { value: "S1", labelKey: "auth.semester_ci_s1", defaultLabel: "1ere annee - Semestre 1 (S1)" },
  { value: "S2", labelKey: "auth.semester_ci_s2", defaultLabel: "1ere annee - Semestre 2 (S2)" },
  { value: "S3", labelKey: "auth.semester_ci_s3", defaultLabel: "2eme annee - Semestre 3 (S3)" },
  { value: "S4", labelKey: "auth.semester_ci_s4", defaultLabel: "2eme annee - Semestre 4 (S4)" },
  { value: "S5", labelKey: "auth.semester_ci_s5", defaultLabel: "3eme annee - Semestre 5 (S5)" },
  { value: "S6", labelKey: "auth.semester_ci_s6", defaultLabel: "3eme annee - Semestre 6 (S6)" },
] as const;

const PREPA_SEMESTERS = [
  { value: "S1", labelKey: "auth.semester_prep_s1", defaultLabel: "1ere annee preparatoire - Semestre 1 (S1)" },
  { value: "S2", labelKey: "auth.semester_prep_s2", defaultLabel: "1ere annee preparatoire - Semestre 2 (S2)" },
  { value: "S3", labelKey: "auth.semester_prep_s3", defaultLabel: "2eme annee preparatoire - Semestre 3 (S3)" },
  { value: "S4", labelKey: "auth.semester_prep_s4", defaultLabel: "2eme annee preparatoire - Semestre 4 (S4)" },
] as const;

function getCurrentAcademicYear(now = new Date()): string {
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const start = month >= 9 ? year : year - 1;
  return `${start}-${start + 1}`;
}

function buildClassLabel(track: string, semester: string): string | null {
  if (!track || !semester) return null;
  const options = track === "2AP" ? PREPA_SEMESTERS : ENGINEERING_SEMESTERS;
  const selected = options.find((item) => item.value === semester);
  if (!selected) return null;
  return `${track}_${getCurrentAcademicYear()}_${selected.value}`;
}

function formatComputedClassLabel(value: string | null): string {
  return value ? value.replace(/_/g, " ") : "";
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
    if (detail) return detail;
  }
  return fallback;
}

export default function LoginPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const auth = useAuthStore();
  const { theme, toggleTheme } = useTheme();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [showRegisterPassword, setShowRegisterPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isPolicyModalOpen, setIsPolicyModalOpen] = useState(false);

  const schema = z.object({
    email: z
      .string()
      .min(1, t("common.email"))
      .refine((v) => isUsmsEmail(v), t("auth.institutional_email_hint")),
    password: z.string().min(1, t("common.password"))
  });

  const registerSchema = z
    .object({
      email: z
        .string()
        .min(1, t("common.email"))
        .refine((v) => isUsmsEmail(v), t("auth.institutional_email_hint")),
      password: z.string().min(8, t("auth.password_hint", { defaultValue: "Au moins 8 caractères, un chiffre et un symbole" })),
      confirmPassword: z.string().min(8, t("auth.password_hint", { defaultValue: "Au moins 8 caractères, un chiffre et un symbole" })),
      track: z.string().min(1, t("auth.select_filiere", { defaultValue: "Selectionnez votre filiere" })),
      semester: z.string().min(1, t("auth.select_level", { defaultValue: "Selectionnez votre semestre" })),
      acceptPrivacy: z.boolean().refine((v) => v, {
        message: t("auth.accept_privacy_required", { defaultValue: "Vous devez accepter la politique de confidentialité." }),
      }),
    })
    .refine((v) => v.password === v.confirmPassword, {
      message: t("auth.password_mismatch", { defaultValue: "Mismatched passwords" }),
      path: ["confirmPassword"]
    });

  type FormValues = z.infer<typeof schema>;
  type RegisterFormValues = z.infer<typeof registerSchema>;

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting }
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const {
    register: registerRegister,
    control: registerControl,
    setValue: setRegisterValue,
    handleSubmit: handleSubmitRegister,
    formState: { errors: registerErrors, isSubmitting: isSubmittingRegister }
  } = useForm<RegisterFormValues>({ resolver: zodResolver(registerSchema) });

  const selectedTrack = useWatch({ control: registerControl, name: "track" });
  const selectedSemester = useWatch({ control: registerControl, name: "semester" });
  const semesterOptions = selectedTrack === "2AP" ? PREPA_SEMESTERS : ENGINEERING_SEMESTERS;
  const computedClassLabel = buildClassLabel(selectedTrack || "", selectedSemester || "");

  useEffect(() => {
    if (!selectedSemester) return;
    const isValidSemester = semesterOptions.some((semester) => semester.value === selectedSemester);
    if (!isValidSemester) setRegisterValue("semester", "");
  }, [semesterOptions, selectedSemester, setRegisterValue]);

  useEffect(() => {
    useAuthStore.getState().hydrate();
  }, []);

  useEffect(() => {
    if (auth.user) {
      router.replace("/chat");
    }
  }, [auth.user, router]);

  const onSubmit = async (values: FormValues) => {
    try {
      await auth.login(values.email, values.password);
      toast.success(t("common.login_success", { defaultValue: "Connexion réussie" }));
      router.push("/chat");
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("common.login_failed", { defaultValue: "Échec de connexion" })));
    }
  };

  const onRegisterSubmit = async (values: RegisterFormValues) => {
    try {
      const classLabel = buildClassLabel(values.track, values.semester);
      await auth.register(values.email, values.password, classLabel, values.acceptPrivacy);
      toast.success(t("common.register_success", { defaultValue: "Inscription réussie" }));
      router.push("/chat");
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("common.register_failed", { defaultValue: "Échec de l'inscription" })));
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center px-4 py-8 md:p-6 bg-background relative overflow-y-auto font-inter">
      <div className="absolute top-0 left-0 right-0 bottom-0 bg-[radial-gradient(circle_at_25%_25%,_#3b82f6_0%,_transparent_50%),_radial-gradient(circle_at_75%_75%,_#6366f1_0%,_transparent_50%)] opacity-[0.03] pointer-events-none" />
      
      {/* Theme & Language Switcher */}
      <div className="fixed top-4 right-4 md:top-6 md:right-6 flex items-center gap-2 md:gap-3 z-50">
        <LanguageSwitcher direction="down" align="right" />
        <button 
          onClick={toggleTheme}
          className="p-2.5 md:p-3 rounded-xl border border-border bg-card shadow-sm hover:bg-muted transition-all"
        >
          {theme === "dark" ? <Sun size={20} className="text-ensa-blue" /> : <Moon size={20} className="text-ensa-navy" />}
        </button>
      </div>

      <div className="w-full max-w-[460px] z-10 animate-in fade-in slide-in-from-bottom-8 duration-700 mt-12 md:mt-0">
        <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-2xl">
          <div className="bg-[#273272] p-7 md:p-9 text-center relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-full bg-[linear-gradient(135deg,_rgba(255,255,255,0.05)_0%,_transparent_100%)]" />
            <div className="bg-white rounded-xl px-4 py-3 min-w-44 h-16 flex items-center justify-center mx-auto mb-4 shadow-lg border-2 border-gray-100/10">
               <GraduationCap size={32} className="text-[#273272]" />
               <span className="ml-2.5 font-poppins font-extrabold text-[#273272] text-lg leading-tight whitespace-nowrap">ENSA BM</span>
            </div>
            <h1 className="font-poppins font-bold text-white text-2xl md:text-3xl tracking-tight mb-1.5">ENSA Béni Mellal</h1>
            <p className="text-blue-100/70 text-xs md:text-sm font-medium">École Nationale des Sciences Appliquées</p>
          </div>

          <div className="p-6 md:p-8 bg-card">
            <div className="text-center mb-8">
              <h2 className="font-poppins font-semibold text-xl md:text-2xl text-foreground mb-2 tracking-tight">
                {mode === "login" ? t("auth.login_title") : t("auth.register_title")}
              </h2>
              <p className="text-muted-foreground text-sm">
                {mode === "login" ? t("auth.login_subtitle") : t("auth.register_subtitle")}
              </p>
            </div>

            <div className="bg-muted/50 p-3.5 rounded-xl border border-blue-100 dark:border-blue-900/30 text-ensa-blue dark:text-blue-300 text-xs flex items-center gap-2.5 mb-8">
              <ShieldCheck size={18} className="shrink-0" />
              <span>{t("auth.secure_connection", { defaultValue: "Vos données institutionnelles sont protégées et sécurisées" })}</span>
            </div>

            <div className="flex gap-2 mb-8 bg-muted p-1 rounded-xl">
              <button
                onClick={() => setMode("login")}
                className={`flex-1 py-2.5 rounded-lg font-poppins font-semibold text-xs transition-all ${
                  mode === "login" ? "bg-card text-foreground shadow-sm border border-border" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t("common.login")}
              </button>
              <button
                onClick={() => setMode("register")}
                className={`flex-1 py-2.5 rounded-lg font-poppins font-semibold text-xs transition-all ${
                  mode === "register" ? "bg-card text-foreground shadow-sm border border-border" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t("common.register")}
              </button>
            </div>

            {mode === "login" ? (
              <form className="space-y-4" onSubmit={handleSubmit(onSubmit)}>
                <div className="space-y-1.5">
                  <label className="flex items-center gap-2 text-xs font-semibold text-foreground/80 mb-1 ml-1">
                    <GraduationCap size={14} className="text-ensa-blue" />
                    {t("common.email")}
                  </label>
                  <div className="relative group">
                    <LogIn className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-ensa-blue transition-colors" size={16} />
                    <input
                      className="w-full bg-muted/30 border border-border pl-10 pr-3.5 py-3 rounded-xl outline-none focus:border-ensa-blue focus:bg-card transition-all text-sm text-foreground placeholder:text-muted-foreground/50"
                      placeholder="prenom.nom@usms.ac.ma"
                      {...register("email")}
                    />
                  </div>
                  {errors.email && <p className="text-[10px] text-destructive font-bold mt-1 ml-1">{errors.email.message}</p>}
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-center gap-2 text-xs font-semibold text-foreground/80 mb-1 ml-1">
                    <IdCard size={14} className="text-ensa-blue" />
                    {t("common.password")}
                  </label>
                  <div className="relative group">
                    <IdCard className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-ensa-blue transition-colors" size={16} />
                    <input
                      type={showLoginPassword ? "text" : "password"}
                      className="w-full bg-muted/30 border border-border pl-10 pr-10 py-3 rounded-xl outline-none focus:border-ensa-blue focus:bg-card transition-all text-sm text-foreground placeholder:text-muted-foreground/50"
                      placeholder="••••••••"
                      {...register("password")}
                    />
                    <button
                      type="button"
                      onClick={() => setShowLoginPassword((prev) => !prev)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-ensa-blue transition-colors"
                      aria-label={showLoginPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                    >
                      {showLoginPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {errors.password && <p className="text-[10px] text-destructive font-bold mt-1 ml-1">{errors.password.message}</p>}
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full bg-ensa-blue hover:bg-ensa-navy text-white py-3.5 rounded-xl font-poppins font-bold text-base transition-all shadow-lg hover:shadow-ensa-blue/20 hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-50 flex items-center justify-center gap-2.5"
                >
                  <LogIn size={18} />
                  {isSubmitting ? t("common.processing", { defaultValue: "..." }) : t("common.login")}
                </button>
              </form>
            ) : (
              <form className="space-y-4" onSubmit={handleSubmitRegister(onRegisterSubmit)}>
                <div className="space-y-1.5">
                  <label className="flex items-center gap-2 text-xs font-semibold text-foreground/80 mb-1 ml-1">
                    <GraduationCap size={14} className="text-ensa-blue" />
                    {t("common.email")}
                  </label>
                  <input
                    className="w-full bg-muted/30 border border-border px-3.5 py-3 rounded-xl outline-none focus:border-ensa-blue focus:bg-card transition-all text-sm text-foreground placeholder:text-muted-foreground/50"
                    placeholder="prenom.nom@usms.ac.ma"
                    {...registerRegister("email")}
                  />
                  {registerErrors.email && <p className="text-[10px] text-destructive font-bold mt-1 ml-1">{registerErrors.email.message}</p>}
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-center gap-2 text-xs font-semibold text-foreground/80 mb-1 ml-1">
                    <BookOpen size={14} className="text-ensa-blue" />
                    {t("auth.track_label", { defaultValue: "Filiere / parcours" })}
                  </label>
                  <select
                    className="w-full bg-muted/30 border border-border px-3.5 py-3 rounded-xl outline-none focus:border-ensa-blue focus:bg-card transition-all text-sm text-foreground appearance-none cursor-pointer"
                    {...registerRegister("track")}
                  >
                    <option value="">{t("auth.select_filiere", { defaultValue: "Sélectionner votre filière" })}</option>
                    {TRACK_OPTIONS.map((c) => (
                      <option key={c} value={c}>{c === "2AP" ? "2AP - Cycle preparatoire" : c}</option>
                    ))}
                  </select>
                  {registerErrors.track && <p className="text-[10px] text-destructive font-bold mt-1 ml-1">{registerErrors.track.message}</p>}
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-center gap-2 text-xs font-semibold text-foreground/80 mb-1 ml-1">
                    <GraduationCap size={14} className="text-ensa-blue" />
                    {t("auth.current_level", { defaultValue: "Semestre actuel" })}
                  </label>
                  <select
                    className="w-full bg-muted/30 border border-border px-3.5 py-3 rounded-xl outline-none focus:border-ensa-blue focus:bg-card transition-all text-sm text-foreground appearance-none cursor-pointer disabled:opacity-60"
                    {...registerRegister("semester")}
                    disabled={!selectedTrack}
                  >
                    <option value="">{t("auth.select_level", { defaultValue: "Selectionner votre semestre" })}</option>
                    {semesterOptions.map((semester) => (
                      <option key={semester.value} value={semester.value}>
                        {t(semester.labelKey, { defaultValue: semester.defaultLabel })}
                      </option>
                    ))}
                  </select>
                  {registerErrors.semester && <p className="text-[10px] text-destructive font-bold mt-1 ml-1">{registerErrors.semester.message}</p>}
                  <p className="text-[10px] font-semibold text-muted-foreground ml-1">
                    {computedClassLabel
                      ? t("auth.computed_class_hint", {
                          defaultValue: "Contexte chatbot : {{classLabel}}",
                          classLabel: formatComputedClassLabel(computedClassLabel),
                        })
                      : t("auth.semester_select_hint", { defaultValue: "Choisissez le semestre exact : 1ere annee = S1/S2, 2eme annee = S3/S4, 3eme annee = S5/S6." })}
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-[10px] font-semibold text-foreground/60 mb-0.5 ml-1">{t("common.password")}</label>
                    <div className="relative group">
                      <input
                        type={showRegisterPassword ? "text" : "password"}
                        className="w-full bg-muted/30 border border-border px-3.5 pr-10 py-3 rounded-xl outline-none focus:border-ensa-blue focus:bg-card transition-all text-sm text-foreground"
                        placeholder="••••••••"
                        {...registerRegister("password")}
                      />
                      <button
                        type="button"
                        onClick={() => setShowRegisterPassword((prev) => !prev)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-ensa-blue transition-colors"
                        aria-label={showRegisterPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                      >
                        {showRegisterPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    {registerErrors.password && <p className="text-[10px] text-destructive font-bold mt-0.5 ml-1">{registerErrors.password.message}</p>}
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] font-semibold text-foreground/60 mb-0.5 ml-1">{t("auth.confirm_password", { defaultValue: "Confirmer" })}</label>
                    <div className="relative group">
                      <input
                        type={showConfirmPassword ? "text" : "password"}
                        className="w-full bg-muted/30 border border-border px-3.5 pr-10 py-3 rounded-xl outline-none focus:border-ensa-blue focus:bg-card transition-all text-sm text-foreground"
                        placeholder="••••••••"
                        {...registerRegister("confirmPassword")}
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword((prev) => !prev)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-ensa-blue transition-colors"
                        aria-label={showConfirmPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                      >
                        {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="rounded-xl border border-border bg-muted/20 p-3 text-xs font-medium text-foreground/80">
                    <div className="flex items-start gap-2.5">
                      <input
                        id="acceptPrivacy"
                        type="checkbox"
                        className="mt-0.5 h-4 w-4 rounded border-border text-ensa-blue focus:ring-ensa-blue"
                        {...registerRegister("acceptPrivacy")}
                      />
                      <div className="leading-relaxed">
                        <label htmlFor="acceptPrivacy" className="cursor-pointer">
                          {t("auth.privacy_policy_accept")}
                        </label>{" "}
                        <button
                          type="button"
                          onClick={() => setIsPolicyModalOpen(true)}
                          className="font-bold text-ensa-blue underline underline-offset-2"
                        >
                          ({t("auth.policies")})
                        </button>
                      </div>
                    </div>
                  </div>
                  {registerErrors.acceptPrivacy && (
                    <p className="text-[10px] text-destructive font-bold mt-0.5 ml-1">{registerErrors.acceptPrivacy.message}</p>
                  )}
                </div>

                <Modal
                  isOpen={isPolicyModalOpen}
                  onClose={() => setIsPolicyModalOpen(false)}
                  title={t("auth.policies")}
                >
                  <PrivacyPolicies />
                </Modal>

                <button
                  type="submit"
                  disabled={isSubmittingRegister}
                  className="w-full bg-ensa-blue hover:bg-ensa-navy text-white py-3.5 rounded-xl font-poppins font-bold text-base transition-all shadow-lg hover:shadow-ensa-blue/20 hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-50 flex items-center justify-center gap-2.5"
                >
                  <LogIn size={18} />
                  {isSubmittingRegister ? t("common.processing", { defaultValue: "..." }) : t("common.register")}
                </button>
              </form>
            )}

            <div className="mt-8 pt-6 border-t border-border">
              <div className="flex items-center gap-3 mb-4">
                <div className="h-px flex-1 bg-border" />
                <span className="text-muted-foreground text-xs font-medium">{t("common.or", { defaultValue: "ou" })}</span>
                <div className="h-px flex-1 bg-border" />
              </div>
              
              <a 
                href="https://ensabm.usms.ac.ma/" 
                target="_blank" 
                className="flex items-center justify-center gap-2 w-full py-3 border border-ensa-blue text-ensa-blue rounded-xl font-poppins font-semibold text-sm hover:bg-ensa-blue hover:text-white transition-all group"
              >
                <HelpCircle size={18} />
                {t("auth.connection_issue", { defaultValue: "Problème de connexion ?" })}
              </a>
              <p className="text-center text-muted-foreground text-[10px] mt-3">
                {t("auth.contact_admin_hint", { defaultValue: "Visitez le site officiel pour contacter l'administration" })}
              </p>
            </div>

            <div className="mt-8 text-center">
              <div className="inline-flex items-center gap-1.5 bg-muted px-3 py-1.5 rounded-full text-ensa-emerald font-bold text-[10px] mb-3">
                <ShieldCheck size={12} />
                {t("auth.secure_connection_badge", { defaultValue: "Connexion sécurisée" })}
              </div>
              <p className="text-muted-foreground/60 text-[10px]">
                © {new Date().getFullYear()} ENSA Béni Mellal · USMS<br/>
                {t("common.rights_reserved", { defaultValue: "Tous droits réservés" })}
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
