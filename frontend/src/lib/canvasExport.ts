'use client';

import type { CanvasContent } from '@/types/canvas';
import {
  buildDataTableCsv,
  buildExportDescriptor,
  buildExportFileName,
  getCanvasContentText,
  getCanvasExportLabel,
  isCanvasContentExportable,
  resolveActiveContent,
  type ExportDescriptor,
  type SupportedExportFormat,
} from '@/lib/canvasExportShared';

export { getCanvasContentText, getCanvasExportLabel, isCanvasContentExportable };
export type { SupportedExportFormat };

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

async function exportMarkdown(markdown: string, fileName: string) {
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  downloadBlob(blob, fileName);
}

async function exportCsv(csv: string, fileName: string) {
  const blob = new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' });
  downloadBlob(blob, fileName);
}

async function exportPdf(content: CanvasContent, descriptor: ExportDescriptor, fileName: string) {
  const activeContent = resolveActiveContent(content);
  const response = await fetch('/api/exports/pdf', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      content: activeContent,
      descriptor,
    }),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || 'PDF 导出失败');
  }

  const blob = await response.blob();
  downloadBlob(blob, fileName);
}

export async function exportCanvasContent(
  content: CanvasContent,
  allContents: CanvasContent[],
  format: SupportedExportFormat
): Promise<string> {
  const descriptor = buildExportDescriptor(content, allContents);
  if (!descriptor) {
    throw new Error('当前交付物暂不支持导出');
  }

  const markdown = getCanvasContentText(content, allContents);
  const fileName = buildExportFileName(descriptor, format);

  if (format === 'csv') {
    const activeContent = resolveActiveContent(content);
    if (activeContent.type !== 'dataTable') {
      throw new Error('当前交付物暂不支持导出 CSV');
    }
    await exportCsv(buildDataTableCsv(activeContent), fileName);
    return fileName;
  }

  if (format === 'md') {
    await exportMarkdown(markdown, fileName);
    return fileName;
  }

  await exportPdf(content, descriptor, fileName);
  return fileName;
}
