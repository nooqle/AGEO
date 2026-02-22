'use client';

import { useState, useCallback, useRef } from 'react';
import type { Attachment } from '@/components/chat/Message/AttachmentCard';
import { api } from '@/services/api';

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_TYPES = [
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
  'application/pdf',
  'text/plain',
  'text/csv',
  'application/json',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
];

interface UseFileUploadOptions {
  maxFiles?: number;
  onError?: (error: string) => void;
}

export function useFileUpload({ maxFiles = 5, onError }: UseFileUploadOptions = {}) {
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const openFilePicker = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const addFiles = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      setIsUploading(true);

      try {
        for (const file of fileArray) {
          // Use functional state check to avoid stale closure
          const shouldStop = await new Promise<boolean>((resolve) => {
            setAttachments((prev) => {
              if (prev.length >= maxFiles) {
                resolve(true);
              } else {
                resolve(false);
              }
              return prev;
            });
          });
          if (shouldStop) {
            onError?.(`Maximum ${maxFiles} files allowed`);
            break;
          }

          if (file.size > MAX_FILE_SIZE) {
            onError?.(`File "${file.name}" exceeds 10MB limit`);
            continue;
          }
          if (!ALLOWED_TYPES.includes(file.type)) {
            onError?.(`File type "${file.type}" is not supported`);
            continue;
          }

          try {
            // Upload to backend
            const result = await api.uploadFile(file);
            const attachment: Attachment = {
              id: result.id,
              name: result.name,
              size: result.size,
              type: result.type,
              url: result.url,
            };
            setAttachments((prev) => [...prev, attachment]);
          } catch (err) {
            // Fallback to local attachment if upload fails
            const attachment: Attachment = {
              id: `file_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
              name: file.name,
              size: file.size,
              type: file.type,
              url: URL.createObjectURL(file),
            };
            setAttachments((prev) => [...prev, attachment]);
            onError?.(err instanceof Error ? err.message : 'Upload failed, using local file');
          }
        }
      } finally {
        setIsUploading(false);
      }
    },
    [maxFiles, onError]
  );

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => {
      const attachment = prev.find((a) => a.id === id);
      if (attachment?.url?.startsWith('blob:')) {
        URL.revokeObjectURL(attachment.url);
      }
      return prev.filter((a) => a.id !== id);
    });
  }, []);

  const clearAttachments = useCallback(() => {
    attachments.forEach((a) => {
      if (a.url?.startsWith('blob:')) URL.revokeObjectURL(a.url);
    });
    setAttachments([]);
  }, [attachments]);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        addFiles(e.target.files);
        // Reset input so same file can be selected again
        e.target.value = '';
      }
    },
    [addFiles]
  );

  return {
    attachments,
    isUploading,
    inputRef,
    openFilePicker,
    addFiles,
    removeAttachment,
    clearAttachments,
    handleFileChange,
  };
}
