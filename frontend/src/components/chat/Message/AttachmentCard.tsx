'use client';

import {
  RiFileTextLine,
  RiImageLine,
  RiFilePdfLine,
  RiFileExcelLine,
  RiFileZipLine,
  RiDownloadLine,
  RiCloseLine,
} from '@remixicon/react';

export interface Attachment {
  id?: string;
  name: string;
  size?: number;
  type?: string | null;
  url?: string;
}

interface AttachmentCardProps {
  attachment: Attachment;
  removable?: boolean;
  onRemove?: () => void;
}

function inferFileType(type?: string | null, name?: string): string {
  const normalizedType = typeof type === 'string' ? type.trim().toLowerCase() : '';
  if (normalizedType) return normalizedType;

  const extension = name?.split('.').pop()?.trim().toLowerCase() ?? '';

  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(extension)) {
    return 'image/unknown';
  }
  if (extension === 'pdf') return 'application/pdf';
  if (['csv', 'xls', 'xlsx'].includes(extension)) return 'application/spreadsheet';
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(extension)) return 'application/zip';

  return '';
}

function FileIcon({ type, name, className }: { type?: string | null; name?: string; className?: string }) {
  const fileType = inferFileType(type, name);

  if (fileType.startsWith('image/')) return <RiImageLine className={className} />;
  if (fileType === 'application/pdf') return <RiFilePdfLine className={className} />;
  if (fileType.includes('spreadsheet') || fileType.includes('excel')) return <RiFileExcelLine className={className} />;
  if (fileType.includes('zip') || fileType.includes('compressed')) return <RiFileZipLine className={className} />;
  return <RiFileTextLine className={className} />;
}

function formatSize(bytes?: number): string {
  if (!Number.isFinite(bytes) || bytes === undefined || bytes < 0) return '--';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentCard({ attachment, removable, onRemove }: AttachmentCardProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg hover:border-[var(--border-hover)] transition-colors group min-w-[180px] max-w-[240px]">
      <FileIcon type={attachment.type} name={attachment.name} className="w-5 h-5 text-[#6366F1] flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-[var(--text-primary)] truncate">{attachment.name}</p>
        <p className="text-[10px] text-[var(--text-tertiary)]">{formatSize(attachment.size)}</p>
      </div>
      {removable && onRemove ? (
        <button
          onClick={onRemove}
          className="p-0.5 hover:bg-[var(--bg-tertiary)] rounded opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <RiCloseLine className="w-3.5 h-3.5 text-[var(--text-tertiary)]" />
        </button>
      ) : attachment.url ? (
        <a
          href={attachment.url}
          download={attachment.name}
          className="p-0.5 hover:bg-[var(--bg-tertiary)] rounded opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <RiDownloadLine className="w-3.5 h-3.5 text-[var(--text-tertiary)]" />
        </a>
      ) : null}
    </div>
  );
}
