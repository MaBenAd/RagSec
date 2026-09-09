"use client";

import { useRouter } from "next/navigation";
import { ChevronLeft, ShieldCheck } from "lucide-react";

export default function PrivacyPage() {
  const router = useRouter();

  return (
    <main className="min-h-screen bg-background text-foreground font-inter">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <button
          onClick={() => router.back()}
          className="mb-6 inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-xs font-bold uppercase tracking-widest hover:bg-muted transition-all"
        >
          <ChevronLeft size={16} />
          Retour
        </button>

        <section className="rounded-3xl border border-border bg-card p-8 shadow-xl space-y-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-ensa-blue/10 text-ensa-blue flex items-center justify-center">
              <ShieldCheck size={20} />
            </div>
            <h1 className="font-poppins text-xl font-bold tracking-tight">Politique de confidentialite</h1>
          </div>

          <p className="text-sm leading-relaxed text-muted-foreground">
            Cette application collecte uniquement les donnees necessaires au fonctionnement du service:
            authentification, conversations et preferences utilisateur. Les donnees ne sont utilisees
            que pour ameliorer la qualite des reponses et assurer la securite du service.
          </p>

          <p className="text-sm leading-relaxed text-muted-foreground">
            Vous pouvez demander la suppression de votre compte depuis la page profil. La suppression
            du compte entraine la suppression des donnees associees dans les limites techniques du systeme.
          </p>

          <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/70">
            Derniere mise a jour: 2026-04-13
          </p>
        </section>
      </div>
    </main>
  );
}
