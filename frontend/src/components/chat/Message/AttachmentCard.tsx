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
  id: string;
  name: string;
  size: number;
  type: string;
  url?: string;
}

interface AttachmentCardProps {
  attachment: Attachment;
  removable?: boolean;
  onRemove?: () => void;
}

function FileIcon({ type, className }: { type: string; className?: string }) {
  if (type.startsWith('image/')) return <RiImageLine className={className} />;
  if (type === 'application/pdf') return <RiFilePdfLine className={className} />;
  if (type.includes('spreadsheet') || type.includes('excel')) return <RiFileExcelLine className={className} />;
  if (type.includes('zip') || type.includes('compressed')) return <RiFileZipLine className={className} />;
  return <RiFileTextLine className={className} />;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentCard({ attachment, removable, onRemove }: AttachmentCardProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-[--bg-elevated] border border-[--border-subtle] rounded-lg hover:border-[--border-hover] transition-colors group min-w-[180px] max-w-[240px]">
      <FileIcon type={attachment.type} className="w-5 h-5 text-[#6366F1] flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-[--text-primary] truncate">{attachment.name}</p>
        <p className="text-[10px] text-[--text-tertiary]">{formatSize(attachment.size)}</p>
      </div>
      {removable && onRemove ? (
        <button
          onClick={onRemove}
          className="p-0.5 hover:bg-[--bg-tertiary] rounded opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <RiCloseLine className="w-3.5 h-3.5 text-[--text-tertiary]" />
        </button>
      ) : attachment.url ? (
        <a
          href={attachment.url}
          download={attachment.name}
          className="p-0.5 hover:bg-[--bg-tertiary] rounded opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <RiDownloadLine className="w-3.5 h-3.5 text-[--text-tertiary]" />
        </a>
      ) : null}
    </div>
  );
}
