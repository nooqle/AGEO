import { NextRequest, NextResponse } from 'next/server';
import type { CanvasContent } from '@/types/canvas';
import type { ExportDescriptor } from '@/lib/canvasExportShared';
import { launchPdfBrowser } from '@/lib/playwrightBrowser';
import {
  createPrintExportEntry,
  deletePrintExportEntry,
} from '@/lib/printExportStore';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type PdfExportRequestBody = {
  content?: CanvasContent;
  descriptor?: ExportDescriptor;
};

export async function POST(request: NextRequest) {
  let exportId: string | null = null;

  try {
    const body = await request.json() as PdfExportRequestBody;
    const content = body.content;
    const descriptor = body.descriptor;

    if (!content || !descriptor) {
      return new NextResponse('缺少导出内容或导出描述', { status: 400 });
    }

    exportId = createPrintExportEntry({ content, descriptor });
    const browser = await launchPdfBrowser();

    try {
      const page = await browser.newPage({
        viewport: { width: 1440, height: 2200 },
        deviceScaleFactor: 2,
      });

      const printUrl = new URL(`/exports/print/${exportId}`, request.nextUrl.origin).toString();
      await page.goto(printUrl, { waitUntil: 'networkidle' });
      await page.waitForFunction(() => document.documentElement.dataset.pdfReady === 'true');
      await page.emulateMedia({ media: 'print' });

      const pdfBuffer = await page.pdf({
        format: 'A4',
        printBackground: true,
        preferCSSPageSize: true,
      });

      return new NextResponse(Buffer.from(pdfBuffer), {
        status: 200,
        headers: {
          'Content-Type': 'application/pdf',
          'Content-Disposition': `attachment; filename="${encodeURIComponent(descriptor.deliverableName)}.pdf"`,
          'Cache-Control': 'no-store',
        },
      });
    } finally {
      await browser.close();
    }
  } catch (error) {
    console.error('PDF export route failed:', error);
    return new NextResponse(
      error instanceof Error ? error.message : 'PDF 导出失败',
      { status: 500 }
    );
  } finally {
    if (exportId) {
      deletePrintExportEntry(exportId);
    }
  }
}
