'use client';

import { AttachmentCard, type Attachment } from './AttachmentCard';

interface AttachmentListProps {
  attachments: Attachment[];
  removable?: boolean;
  onRemove?: (id: string) => void;
}

function getAttachmentKey(attachment: Attachment, index: number): string {
  const rawId = typeof attachment.id === 'string' ? attachment.id.trim() : '';
  if (rawId) return `id:${rawId}:${index}`;

  const rawUrl = typeof attachment.url === 'string' ? attachment.url.trim() : '';
  if (rawUrl) return `url:${rawUrl}:${index}`;

  const rawName = attachment.name.trim();
  const rawSize = Number.isFinite(attachment.size) ? attachment.size : 'na';
  return `fallback:${rawName}:${rawSize}:${index}`;
}

export function AttachmentList({ attachments, removable, onRemove }: AttachmentListProps) {
  if (!attachments || attachments.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {attachments.map((attachment, index) => (
        <AttachmentCard
          key={getAttachmentKey(attachment, index)}
          attachment={attachment}
          removable={removable}
          onRemove={onRemove && attachment.id ? () => onRemove(attachment.id as string) : undefined}
        />
      ))}
    </div>
  );
}
