'use client';

import { AttachmentCard, type Attachment } from './AttachmentCard';

interface AttachmentListProps {
  attachments: Attachment[];
  removable?: boolean;
  onRemove?: (id: string) => void;
}

export function AttachmentList({ attachments, removable, onRemove }: AttachmentListProps) {
  if (!attachments || attachments.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {attachments.map((attachment) => (
        <AttachmentCard
          key={attachment.id}
          attachment={attachment}
          removable={removable}
          onRemove={onRemove ? () => onRemove(attachment.id) : undefined}
        />
      ))}
    </div>
  );
}
