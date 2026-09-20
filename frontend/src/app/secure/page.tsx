"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { securityLogin, securityToken } from "@/lib/security-api";
import { useSecurityStore } from "@/store/useSecurityStore";

export default function SecureChat() {
  const { t, i18n } = useTranslation();
  const store = useSecurityStore();
  const [signedIn, setSignedIn] = useState(false);
  const [email, setEmail] = useState("alice@example.test");
  const [password, setPassword] = useState("");
  const [question, setQuestion] = useState("");
  const [stream, setStream] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => setSignedIn(Boolean(securityToken())), []);
  async function login(event: FormEvent) {
    event.preventDefault(); setError("");
    try { await securityLogin(email, password); setPassword(""); setSignedIn(true); }
    catch { setError(t("common.login_failed")); }
  }
  async function send(event: FormEvent) {
    event.preventDefault(); setError("");
    try { await store.send(question, i18n.language.slice(0, 2), stream); setQuestion(""); }
    catch { setError(t("security.unavailable")); }
  }
  return <main className="mx-auto max-w-4xl p-6 space-y-6" dir={i18n.language.startsWith("ar") ? "rtl" : "ltr"}>
    <header className="flex flex-wrap items-center justify-between gap-4">
      <h1 className="text-2xl font-bold">RagSec · {t("security.demo")}</h1>
      <select aria-label="Language" value={i18n.language.slice(0, 2)} onChange={e => i18n.changeLanguage(e.target.value)}>
        <option value="en">English</option><option value="fr">Français</option><option value="ar">العربية</option>
      </select>
      <Link href="/secure/admin">{t("admin.console")}</Link>
    </header>
    <p>{t("security.scope")}</p>
    {!signedIn ? <form onSubmit={login} className="flex flex-col gap-3 max-w-md">
      <label>{t("common.email")}<input className="block w-full border p-2" type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label>
      <label>{t("common.password")}<input className="block w-full border p-2" type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
      <button className="rounded bg-blue-700 text-white p-2">{t("common.login")}</button>
    </form> : <>
      <div className="flex gap-4"><button onClick={() => store.reset()}>{t("chat.new_discussion")}</button>
        <button onClick={() => { store.logout(); setSignedIn(false); }}>{t("common.logout")}</button>
        <label><input type="checkbox" checked={stream} onChange={e => setStream(e.target.checked)} /> SSE</label></div>
      <section aria-live="polite">{store.messages.map(message => <MessageBubble key={message.id} message={message} />)}</section>
      <form onSubmit={send} className="flex gap-2">
        <input aria-label={t("chat.placeholder")} className="flex-1 border p-3" maxLength={4096} value={question} onChange={e => setQuestion(e.target.value)} required />
        <button className="rounded bg-blue-700 text-white p-3" disabled={store.busy}>{t("common.send")}</button>
        {store.busy && <button type="button" onClick={() => store.controller?.abort()}>{t("common.cancel")}</button>}
      </form>
    </>}
    {error && <p role="alert">{error}</p>}
  </main>;
}
