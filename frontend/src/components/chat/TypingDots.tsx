import { useTranslation } from "react-i18next";

export function TypingDots() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-2 py-1">
      <div className="flex gap-1.5">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-foreground/20" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-foreground/40 [animation-delay:0.2s]" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-foreground/60 [animation-delay:0.4s]" />
      </div>
      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground animate-pulse">
        {t("common.typing")}
      </span>
    </div>
  );
}
