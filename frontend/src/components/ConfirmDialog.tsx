"use client";

import { AlertTriangle, X } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  variant?: "danger" | "default";
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  loading = false,
  variant = "danger",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  const danger = variant === "danger";

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-card shadow-2xl animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-start justify-between gap-4 border-b border-border p-4">
          <div className="flex items-start gap-3">
            <div className={`rounded-xl p-2 ${danger ? "bg-destructive/10 text-destructive" : "bg-ensa-blue/10 text-ensa-blue"}`}>
              <AlertTriangle size={18} />
            </div>
            <div>
              <h2 className="text-sm font-black uppercase tracking-widest text-foreground">{title}</h2>
              <p className="mt-1 text-xs font-medium leading-relaxed text-muted-foreground">{description}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="rounded-lg border border-border p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            title={cancelLabel}
          >
            <X size={14} />
          </button>
        </div>
        <div className="flex gap-2 p-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="flex-1 rounded-xl border border-border bg-card py-2 text-xs font-bold uppercase tracking-widest hover:bg-muted disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`flex-1 rounded-xl py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-50 ${
              danger ? "bg-destructive hover:bg-destructive/90" : "bg-ensa-blue hover:bg-ensa-navy"
            }`}
          >
            {loading ? "..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
