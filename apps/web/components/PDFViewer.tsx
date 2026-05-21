"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/esm/Page/AnnotationLayer.css";
import "react-pdf/dist/esm/Page/TextLayer.css";

// CDN worker avoids webpack/Next.js bundling issues with pdfjs-dist.
pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

// ── Types ─────────────────────────────────────────────────────────────────────

interface FieldCoords {
  x:      number | null;
  y:      number | null;
  width:  number | null;
  height: number | null;
}

export interface PDFField {
  id:         string;
  name:       string;
  label:      string;
  pageNumber: number;   // 1-indexed
  coords:     FieldCoords;
}

interface PageDims {
  width:  number;   // natural width in PDF user units (points)
  height: number;   // natural height in PDF user units (points)
}

export interface PDFViewerProps {
  pdfUrl:           string;
  fields:           PDFField[];
  answeredNames:    Set<string>;
  skippedNames?:    Set<string>;
  currentFieldName?: string | null;
}

// ── Field overlay ─────────────────────────────────────────────────────────────

function FieldHighlights({
  fields,
  dims,
  pageNumber,
  answeredNames,
  skippedNames,
  currentFieldName,
}: {
  fields:           PDFField[];
  dims:             PageDims;
  pageNumber:       number;
  answeredNames:    Set<string>;
  skippedNames:     Set<string>;
  currentFieldName: string | null;
}) {
  const pageFields = fields.filter(f => f.pageNumber === pageNumber);

  return (
    // Covers the full rendered page; pointer-events:none so clicks pass through.
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {pageFields.map(field => {
        const { x, y, width, height } = field.coords;
        if (x == null || y == null || !width || !height) return null;

        // ── Coordinate conversion ──────────────────────────────────────────
        // AcroForm origin: bottom-left corner of the page, y increases upward.
        // CSS origin:      top-left corner of the container, y increases downward.
        //
        // screenY_top = (pageHeight - acrY - fieldHeight) / pageHeight * 100%
        const leftPct   = (x                           / dims.width)  * 100;
        const topPct    = ((dims.height - y - height)  / dims.height) * 100;
        const widthPct  = (width                       / dims.width)  * 100;
        const heightPct = (height                      / dims.height) * 100;

        const isCurrent  = field.name === currentFieldName;
        const isAnswered = answeredNames.has(field.name);
        const isSkipped  = skippedNames.has(field.name);

        let cls = "absolute rounded-[2px] border transition-colors";
        if (isCurrent) {
          cls += " border-blue-500 bg-blue-400/20 shadow-[0_0_0_2px_rgba(59,130,246,0.4)] animate-pulse";
        } else if (isAnswered) {
          cls += " border-green-400 bg-green-400/15";
        } else if (isSkipped) {
          cls += " border-gray-300 bg-gray-200/20";
        } else {
          cls += " border-gray-300/50 bg-transparent";
        }

        return (
          <div
            key={field.id}
            className={cls}
            style={{
              left:   `${leftPct}%`,
              top:    `${topPct}%`,
              width:  `${widthPct}%`,
              height: `${heightPct}%`,
            }}
          />
        );
      })}
    </div>
  );
}

// ── Loading skeleton (looks like a stacked PDF) ───────────────────────────────

function PDFSkeleton() {
  return (
    <div className="flex flex-col items-center gap-4 py-4">
      {[0, 1].map(i => (
        <div
          key={i}
          className="w-full max-w-[600px] rounded bg-gray-100 animate-pulse shadow"
          style={{ aspectRatio: "8.5 / 11" }}
        />
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function PDFViewer({
  pdfUrl,
  fields,
  answeredNames,
  skippedNames  = new Set(),
  currentFieldName = null,
}: PDFViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs     = useRef<Record<number, HTMLDivElement | null>>({});

  const [numPages,       setNumPages]       = useState<number | null>(null);
  const [pageDims,       setPageDims]       = useState<Record<number, PageDims>>({});
  const [containerWidth, setContainerWidth] = useState(600);
  const [loading,        setLoading]        = useState(true);
  const [docError,       setDocError]       = useState<string | null>(null);

  // Track container width for responsive page rendering.
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width;
      if (w) setContainerWidth(Math.floor(w));
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Scroll to the page that contains the active field.
  useEffect(() => {
    if (!currentFieldName) return;
    const field = fields.find(f => f.name === currentFieldName);
    if (!field) return;
    const el = pageRefs.current[field.pageNumber];
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [currentFieldName, fields]);

  const pageWidth = Math.min(containerWidth - 16, 800);

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-y-auto bg-gray-100">
      {loading && <PDFSkeleton />}

      {docError && (
        <div className="p-6 text-sm text-red-600 text-center">{docError}</div>
      )}

      <Document
        file={pdfUrl}
        onLoadSuccess={({ numPages: n }) => { setNumPages(n); setLoading(false); }}
        onLoadError={err  => { setDocError("Could not load PDF."); setLoading(false); console.error(err); }}
        className="flex flex-col items-center gap-4 py-4"
        loading={null}
      >
        {numPages &&
          Array.from({ length: numPages }, (_, i) => i + 1).map(pageNum => (
            <div
              key={pageNum}
              ref={el => { pageRefs.current[pageNum] = el; }}
              className="relative shadow-md"
              style={{ display: "inline-block" }}
            >
              <Page
                pageNumber={pageNum}
                width={pageWidth}
                renderAnnotationLayer={false}
                renderTextLayer={false}
                onLoadSuccess={(page: any) => {
                  // page.view = [x1, y1, x2, y2] in PDF user units (points).
                  // For standard pages x1=y1=0, x2=width, y2=height.
                  const [x1, y1, x2, y2] = page.view as number[];
                  setPageDims(prev => ({
                    ...prev,
                    [pageNum]: { width: x2 - x1, height: y2 - y1 },
                  }));
                }}
              />

              {pageDims[pageNum] && (
                <FieldHighlights
                  fields={fields}
                  dims={pageDims[pageNum]}
                  pageNumber={pageNum}
                  answeredNames={answeredNames}
                  skippedNames={skippedNames}
                  currentFieldName={currentFieldName}
                />
              )}
            </div>
          ))}
      </Document>
    </div>
  );
}
