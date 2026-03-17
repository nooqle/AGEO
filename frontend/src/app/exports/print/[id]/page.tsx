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
    background: var(--bg-primary);
  }

  body {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .pdf-print-root {
    min-height: 100vh;
  }

  .pdf-print-root a {
    color: inherit;
    text-decoration: none;
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
