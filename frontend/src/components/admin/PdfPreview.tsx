"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2, ZoomIn, ZoomOut } from "lucide-react";

type PdfDocument = Awaited<ReturnType<typeof import("pdfjs-dist").getDocument>> extends { promise: infer P }
  ? Awaited<P>
  : never;

type PdfPreviewProps = {
  url: string;
  filename: string;
};

export function PdfPreview({ url, filename }: PdfPreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);
  const [pdf, setPdf] = useState<PdfDocument | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1.15);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setPdf(null);
    setPageCount(0);
    setPageNumber(1);

    async function loadPdf() {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url
        ).toString();

        const documentTask = pdfjs.getDocument(url);
        const document = await documentTask.promise;
        if (cancelled) {
          document.destroy();
          return;
        }

        setPdf(document as PdfDocument);
        setPageCount(document.numPages);
        setStatus("ready");
      } catch {
        if (!cancelled) setStatus("error");
      }
    }

    loadPdf();

    return () => {
      cancelled = true;
      renderTaskRef.current?.cancel();
      renderTaskRef.current = null;
    };
  }, [url]);

  useEffect(() => {
    if (!pdf || !canvasRef.current || !containerRef.current) return;
    const currentPdf = pdf;

    let cancelled = false;

    async function renderPage() {
      try {
        renderTaskRef.current?.cancel();
        const page = await currentPdf.getPage(pageNumber);
        if (cancelled || !canvasRef.current || !containerRef.current) return;

        const baseViewport = page.getViewport({ scale: 1 });
        const availableWidth = Math.max(containerRef.current.clientWidth - 32, 320);
        const responsiveScale = Math.min((availableWidth / baseViewport.width) * scale, 2.2);
        const viewport = page.getViewport({ scale: responsiveScale });
        const canvas = canvasRef.current;
        const context = canvas.getContext("2d");
        if (!context) return;

        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;

        const task = page.render({ canvasContext: context, viewport });
        renderTaskRef.current = task;
        await task.promise;
      } catch (error) {
        if ((error as { name?: string }).name !== "RenderingCancelledException") {
          setStatus("error");
        }
      }
    }

    renderPage();

    return () => {
      cancelled = true;
      renderTaskRef.current?.cancel();
      renderTaskRef.current = null;
    };
  }, [pdf, pageNumber, scale]);

  if (status === "loading") {
    return (
      <div className="h-[70vh] rounded-xl border border-border bg-white flex items-center justify-center text-xs font-bold text-muted-foreground uppercase tracking-widest">
        <Loader2 size={18} className="mr-2 animate-spin" />
        Chargement du PDF...
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="h-[70vh] rounded-xl border border-border bg-white flex items-center justify-center text-xs font-bold text-destructive uppercase tracking-widest">
        Impossible d&apos;afficher ce PDF
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-white overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-border bg-muted/20 px-3 py-2 text-foreground">
        <div className="min-w-0 text-[10px] font-bold uppercase tracking-wider truncate">
          {filename}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setScale((value) => Math.max(0.8, value - 0.15))}
            className="p-1.5 border border-border rounded-md hover:bg-muted transition-all"
            title="Reduire"
          >
            <ZoomOut size={13} />
          </button>
          <button
            type="button"
            onClick={() => setScale((value) => Math.min(1.8, value + 0.15))}
            className="p-1.5 border border-border rounded-md hover:bg-muted transition-all"
            title="Agrandir"
          >
            <ZoomIn size={13} />
          </button>
          <button
            type="button"
            onClick={() => setPageNumber((value) => Math.max(1, value - 1))}
            disabled={pageNumber <= 1}
            className="p-1.5 border border-border rounded-md hover:bg-muted transition-all disabled:opacity-40"
            title="Page precedente"
          >
            <ChevronLeft size={13} />
          </button>
          <span className="min-w-16 text-center text-[10px] font-bold uppercase tracking-wider">
            {pageNumber}/{pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPageNumber((value) => Math.min(pageCount, value + 1))}
            disabled={pageNumber >= pageCount}
            className="p-1.5 border border-border rounded-md hover:bg-muted transition-all disabled:opacity-40"
            title="Page suivante"
          >
            <ChevronRight size={13} />
          </button>
        </div>
      </div>
      <div ref={containerRef} className="h-[70vh] overflow-auto bg-neutral-100 p-4 custom-scrollbar">
        <canvas ref={canvasRef} className="mx-auto shadow-lg bg-white" />
      </div>
    </div>
  );
}
