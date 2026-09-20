"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { securityRequest } from "@/lib/security-api";

type Document = { id: string; version: number; status: string; classification: string; signals: string[] };

export default function SecureAdmin() {
  const { t, i18n } = useTranslation();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [source, setSource] = useState("source-alpha");
  const [text, setText] = useState("");
  const [classification, setClassification] = useState("public");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setDocuments(await (await securityRequest("/api/v1/admin/documents")).json()); }
    catch { setError(t("security.admin_login")); }
  }, [t]);
  useEffect(() => { void load(); }, [load]);
  async function action(path: string, method = "POST", body?: object) {
    setBusy(true); setError("");
    try { await securityRequest(path, { method, body: body ? JSON.stringify(body) : undefined }); await load(); }
    catch { setError(t("security.operation_failed")); }
    finally { setBusy(false); }
  }
  async function upload(event: FormEvent) {
    event.preventDefault();
    await action("/api/v1/admin/documents", "POST", { source_id: source, classification, text });
  }
  return <main className="mx-auto max-w-4xl p-6 space-y-5" dir={i18n.language.startsWith("ar") ? "rtl" : "ltr"}>
    <h1 className="text-2xl font-bold">RagSec · {t("admin.console")}</h1><Link href="/secure">{t("common.back_to_chat")}</Link>
    <p>{t("security.review_hint")}</p>
    <form onSubmit={upload} className="space-y-3">
      <label>{t("security.source")}<input className="border p-2 ml-2" value={source} onChange={e => setSource(e.target.value)} required /></label>
      <button type="button" disabled={busy} onClick={() => action("/api/v1/admin/sources", "POST", { source_id: source })}>{t("security.register_source")}</button>
      <select aria-label="Classification" value={classification} onChange={e => setClassification(e.target.value)}>
        <option value="public">public</option><option value="private">private</option><option value="restricted">restricted</option>
      </select>
      <textarea aria-label={t("security.document")} className="w-full border p-3" rows={5} maxLength={32768} value={text} onChange={e => setText(e.target.value)} required />
      <button className="rounded bg-blue-700 text-white p-2" disabled={busy}>{t("security.stage")}</button>
    </form>
    <button disabled={busy} onClick={() => action("/api/v1/admin/publish")}>{t("security.publish")}</button>
    <ul className="space-y-3">{documents.map(doc => <li className="border rounded p-3" key={doc.id}>
      <code>{doc.id}</code> · {doc.classification} · {t(`security.${doc.status}`)}
      {doc.signals.length > 0 && <p>{t("security.flagged")}</p>}
      {["scanned", "quarantined"].includes(doc.status) && <div className="flex gap-3">
        <button disabled={busy} onClick={() => action(`/api/v1/admin/documents/${doc.id}/review`, "POST", { version: doc.version, approve: true })}>{t("admin.approve")}</button>
        <button disabled={busy} onClick={() => action(`/api/v1/admin/documents/${doc.id}/review`, "POST", { version: doc.version, approve: false })}>{t("admin.reject")}</button>
      </div>}
      {!["deleted", "revoked"].includes(doc.status) && <button disabled={busy} onClick={() => action(`/api/v1/admin/documents/${doc.id}`, "DELETE")}>{t("admin.delete")}</button>}
    </li>)}</ul>
    {error && <p role="alert">{error}</p>}
  </main>;
}
