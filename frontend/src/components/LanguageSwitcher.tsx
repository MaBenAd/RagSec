"use client";

import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/store/useAuthStore";
import { Languages, Check } from "lucide-react";
import { useState, useRef, useEffect } from "react";

const LANGUAGES = [
  { code: "fr", label: "Francais", flag: "FR" },
  { code: "en", label: "English", flag: "EN" },
  { code: "ar", label: "Arabic", flag: "AR" },
];

interface LanguageSwitcherProps {
  isCollapsed?: boolean;
  direction?: "up" | "down";
  align?: "left" | "right" | "center";
  fullWidth?: boolean;
}

export function LanguageSwitcher({
  isCollapsed = false,
  direction = "up",
  align = "center",
  fullWidth = false,
}: LanguageSwitcherProps) {
  const { i18n } = useTranslation();
  const { setLanguage } = useAuthStore();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLanguageChange = async (code: string) => {
    await setLanguage(code);
    setIsOpen(false);
  };

  const currentLang = LANGUAGES.find((language) => language.code === i18n.language) || LANGUAGES[0];

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`
          flex items-center justify-center gap-1.5 border border-border rounded-xl hover:bg-muted transition-all
          ${isCollapsed ? "h-10 w-10" : "px-3 py-2 min-w-[50px]"}
          ${fullWidth ? "w-full" : ""}
        `}
        title="Changer de langue"
      >
        <Languages size={16} className="text-muted-foreground" />
        {!isCollapsed && <span className="text-[9px] font-bold uppercase tracking-widest">{currentLang.code}</span>}
      </button>

      {isOpen && (
        <div
          className={`
            absolute bg-card border border-border rounded-xl shadow-xl z-[100] overflow-hidden min-w-[120px]
            ${direction === "up" ? "bottom-full mb-2" : "top-full mt-2"}
            ${align === "center" ? "left-1/2 -translate-x-1/2" : align === "right" ? "right-0" : "left-0"}
          `}
        >
          <div className="p-1 flex flex-col gap-0.5">
            {LANGUAGES.map((language) => (
              <button
                key={language.code}
                onClick={() => handleLanguageChange(language.code)}
                className={`
                  flex items-center justify-between px-2.5 py-2 rounded-lg text-[11px] font-bold transition-all
                  ${i18n.language === language.code
                    ? "bg-ensa-blue text-white"
                    : "hover:bg-muted text-foreground/70"}
                `}
              >
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-black uppercase tracking-widest">{language.flag}</span>
                  <span>{language.label}</span>
                </div>
                {i18n.language === language.code && <Check size={12} />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
