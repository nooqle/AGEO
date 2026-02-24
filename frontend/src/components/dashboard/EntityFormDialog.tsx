'use client';

import { useState, useEffect, useCallback } from 'react';
import { RiCloseLine } from '@remixicon/react';
import { AliasTagInput } from './AliasTagInput';
import type { Entity, CreateEntityInput } from '@/types/entity';

interface EntityFormDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: CreateEntityInput) => void;
  entity?: Entity | null;
}

export function EntityFormDialog({
  open,
  onClose,
  onSubmit,
  entity,
}: EntityFormDialogProps) {
  if (!open) return null;

  return (
    <EntityFormDialogInner
      key={entity?.id ?? 'new'}
      entity={entity}
      onClose={onClose}
      onSubmit={onSubmit}
    />
  );
}

function EntityFormDialogInner({
  entity,
  onClose,
  onSubmit,
}: {
  entity?: Entity | null;
  onClose: () => void;
  onSubmit: (data: CreateEntityInput) => void;
}) {
  const [name, setName] = useState(entity?.name ?? '');
  const [aliases, setAliases] = useState<string[]>(entity?.aliases ?? []);
  const [domain, setDomain] = useState(entity?.domain ?? '');
  const [industry, setIndustry] = useState(entity?.industry ?? '');
  const [description, setDescription] = useState(entity?.description ?? '');

  const isEdit = !!entity;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ name, aliases, domain, industry, description });
  };

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="rounded-xl w-full max-w-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-default)',
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ borderBottom: '1px solid var(--border-default)' }}
        >
          <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            {isEdit ? '编辑品牌' : '新建品牌'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 rounded-lg transition-colors cursor-pointer"
            style={{ color: 'var(--text-tertiary)' }}
          >
            <RiCloseLine className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
              品牌名称 *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none transition-colors"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
              }}
              placeholder="例如：华为"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
              品牌别名
            </label>
            <AliasTagInput
              aliases={aliases}
              onChange={setAliases}
              placeholder="输入品牌别名..."
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
              官网 *
            </label>
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none transition-colors"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
              }}
              placeholder="例如：huawei.com"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
              品类 *
            </label>
            <input
              type="text"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none transition-colors"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
              }}
              placeholder="例如：护肤品"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
              品牌描述
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none transition-colors resize-none"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
              }}
              placeholder="简要描述品牌信息..."
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm transition-colors cursor-pointer"
              style={{ color: 'var(--text-secondary)' }}
            >
              取消
            </button>
            <button
              type="submit"
              disabled={!name.trim() || !domain.trim() || !industry.trim()}
              className="btn-primary px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              {isEdit ? '更新品牌' : '创建品牌'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
