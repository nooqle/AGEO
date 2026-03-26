'use client';

import { useState, useCallback, useRef } from 'react';
import type { Attachment } from '@/components/chat/Message/AttachmentCard';
import { api } from '@/services/api';

const MAX_FILE_SIZE = 2 * 1024 * 1024; // 2MB
const MAX_FILE_SIZE_LABEL = '2MB';
const ALLOWED_TYPES = [
  'text/csv',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
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

  const isAllowedFile = useCallback((file: File) => {
    const lowerName = file.name.toLowerCase();
    if (lowerName.endsWith('.csv') || lowerName.endsWith('.xlsx')) {
      return true;
    }
    return ALLOWED_TYPES.includes(file.type);
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
            onError?.(`一次最多上传 ${maxFiles} 个表格`);
            break;
          }

          if (file.size > MAX_FILE_SIZE) {
            onError?.(`文件「${file.name}」超过 ${MAX_FILE_SIZE_LABEL} 限制`);
            continue;
          }
          if (!isAllowedFile(file)) {
            onError?.(`仅支持上传 CSV 或 XLSX 表格`);
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
            onError?.(err instanceof Error ? err.message : '上传失败，请重试');
          }
        }
      } finally {
        setIsUploading(false);
      }
    },
    [isAllowedFile, maxFiles, onError]
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
