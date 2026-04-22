import { notFound } from 'next/navigation';
import { PrintCanvasContent } from '@/components/canvas/contents/PrintCanvasContent';
import { getPrintExportEntry } from '@/lib/printExportStore';

export const dynamic = 'force-dynamic';

const PRINT_PAGE_CSS = `
  @page {
    size: A4;
    margin: 12mm 10mm 14mm;
  }

  html, body {
    margin: 0;
    background: #ffffff;
  }

  body {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
    color: #111827;
  }

  .pdf-print-root {
    min-height: 100vh;
    background: #ffffff;
    color: #111827;
    --bg-primary: #ffffff;
    --bg-secondary: #f8fafc;
    --bg-tertiary: #ffffff;
    --bg-elevated: #f8fafc;
    --text-primary: #111827;
    --text-secondary: #475569;
    --text-tertiary: #64748b;
    --text-disabled: #94a3b8;
    --text-muted: #94a3b8;
    --text-accent: #1d4ed8;
    --brand-primary: #1d4ed8;
    --brand-hover: #2563eb;
    --brand-active: #1e40af;
    --brand-bg: rgba(29, 78, 216, 0.08);
    --brand-border: rgba(29, 78, 216, 0.2);
    --brand-text: #1d4ed8;
    --success: #15803d;
    --warning: #b45309;
    --error: #b91c1c;
    --info: #1d4ed8;
    --border-default: rgba(15, 23, 42, 0.12);
    --border-hover: rgba(15, 23, 42, 0.18);
    --border-focus: #1d4ed8;
    --border-subtle: rgba(15, 23, 42, 0.08);
    --border-strong: rgba(15, 23, 42, 0.18);
  }

  .pdf-print-root a {
    color: var(--text-accent);
    text-decoration: underline;
  }

  .pdf-print-root section,
  .pdf-print-root article,
  .pdf-print-root .rounded-\\[24px\\],
  .pdf-print-root .rounded-\\[28px\\],
  .pdf-print-root .rounded-\\[30px\\],
  .pdf-print-root .rounded-\\[32px\\] {
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .pdf-print-root button {
    cursor: default !important;
  }

  .pdf-print-root [data-print-hidden="true"] {
    display: none !important;
  }

  .pdf-print-root .report-markdown {
    color: var(--text-primary);
  }
`;

export default async function PrintExportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const payload = getPrintExportEntry(id);

  if (!payload) {
    notFound();
  }

  return (
    <>
      <style>{PRINT_PAGE_CSS}</style>
      <main className="pdf-print-root">
        <PrintCanvasContent content={payload.content} />
      </main>
    </>
  );
}
