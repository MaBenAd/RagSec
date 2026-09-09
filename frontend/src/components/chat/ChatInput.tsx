"use client";

import { KeyboardEvent, useState, useRef, useEffect } from "react";
import { SendHorizontal, Command, Square } from "lucide-react";
import { useTranslation } from "react-i18next";

export function ChatInput({
  disabled,
  onCancel,
  onSend,
}: {
  disabled?: boolean;
  onCancel?: () => void;
  onSend: (message: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "inherit";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [text]);

  const submit = async () => {
    const value = text.trim();
    if (!value || disabled) return;
    setText("");
    await onSend(value);
  };

  const handleKeyDown = async (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      await submit();
    }
  };

  return (
    <div className="relative group">
      <div className="bg-card border border-border shadow-xl rounded-2xl p-1.5 transition-all group-focus-within:border-ensa-blue group-focus-within:shadow-ensa-blue/10">
        <div className="flex items-end gap-2">
          <div className="hidden sm:flex p-2.5 text-muted-foreground/40">
            <Command size={16} />
          </div>
          
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder={t("chat.input_placeholder", { defaultValue: "Posez votre question ici..." })}
            className="flex-1 max-h-32 min-h-[44px] bg-transparent px-1.5 py-2.5 text-[14px] font-medium outline-none resize-none placeholder:text-muted-foreground/40 custom-scrollbar"
            disabled={disabled}
          />
          
          <button
            onClick={disabled && onCancel ? onCancel : submit}
            disabled={disabled ? !onCancel : !text.trim()}
            title={disabled && onCancel ? "Arreter la generation" : "Envoyer"}
            className={`
              p-3 rounded-xl transition-all flex items-center justify-center shadow-lg
              ${disabled && onCancel
                ? "text-white bg-ensa-orange hover:bg-ensa-navy shadow-ensa-blue/20"
                : disabled || !text.trim() 
                ? "text-muted-foreground bg-muted cursor-not-allowed opacity-50 shadow-none" 
                : "text-white bg-ensa-blue hover:bg-ensa-navy hover:-translate-y-0.5 active:translate-y-0 shadow-ensa-blue/20"}
            `}
          >
            {disabled && onCancel ? <Square size={18} fill="currentColor" /> : <SendHorizontal size={18} />}
          </button>
        </div>
      </div>
      
      <div className="flex flex-col sm:flex-row justify-between items-center px-4 mt-2.5 gap-1.5">
        <p className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground/40 text-center sm:text-left">
          {t("chat.disclaimer")}
        </p>
        {text.length > 0 && (
          <p className="text-[9px] font-bold uppercase tracking-widest text-ensa-blue/60 animate-in fade-in slide-in-from-right-2">
            {text.length} caracteres
          </p>
        )}
      </div>
    </div>
  );
}
