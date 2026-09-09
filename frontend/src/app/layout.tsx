import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { I18nProvider } from "@/components/providers/I18nProvider";
import { Toaster } from "sonner";

const inter = Inter({ 
  subsets: ["latin"],
  variable: "--font-inter",
});

const poppins = Poppins({
  weight: ["400", "500", "600", "700", "800"],
  subsets: ["latin"],
  variable: "--font-poppins",
});

export const metadata: Metadata = {
  title: "Espace Étudiant — Chatbot ENSA Béni Mellal",
  description: "Assistant universitaire intelligent pour les étudiants de l'ENSA Béni Mellal.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" suppressHydrationWarning className={`${inter.variable} ${poppins.variable}`}>
      <body className={inter.className}>
        <I18nProvider>
          <ThemeProvider>
            {children}
            <Toaster richColors position="top-right" closeButton />
          </ThemeProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
