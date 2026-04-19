'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { RiCloseLine } from '@remixicon/react';
import { AliasTagInput } from './AliasTagInput';
import { modalScrimClassName } from '@/components/ui/modal-scrim';
import type { Entity, CreateEntityInput } from '@/types/entity';

interface EntityFormDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: CreateEntityInput) => void;
  entity?: Entity | null;
  allowOrganizationScope?: boolean;
  preventClose?: boolean;
  onPreventClose?: () => void;
}

export function EntityFormDialog({
  open,
  onClose,
  onSubmit,
  entity,
  allowOrganizationScope = false,
  preventClose = false,
  onPreventClose,
}: EntityFormDialogProps) {
  if (!open) return null;

  return (
    <EntityFormDialogInner
      key={entity?.id ?? 'new'}
      entity={entity}
      onClose={onClose}
      onSubmit={onSubmit}
      allowOrganizationScope={allowOrganizationScope}
      preventClose={preventClose}
      onPreventClose={onPreventClose}
    />
  );
}

function EntityFormDialogInner({
  entity,
  onClose,
  onSubmit,
  allowOrganizationScope,
  preventClose,
  onPreventClose,
}: {
  entity?: Entity | null;
  onClose: () => void;
  onSubmit: (data: CreateEntityInput) => void;
  allowOrganizationScope: boolean;
  preventClose: boolean;
  onPreventClose?: () => void;
}) {
  const lastPreventCloseAtRef = useRef(0);
  const [name, setName] = useState(entity?.name ?? '');
  const [aliases, setAliases] = useState<string[]>(entity?.aliases ?? []);
  const [domain, setDomain] = useState(entity?.domain ?? '');
  const [industry, setIndustry] = useState(entity?.industry ?? '');
  const [description, setDescription] = useState(entity?.description ?? '');
  const [visibilityScope, setVisibilityScope] = useState<CreateEntityInput['visibilityScope']>(
    entity?.visibilityScope ?? 'personal'
  );

  const isEdit = !!entity;

  const handleRequestClose = useCallback(() => {
    if (preventClose) {
      const now = Date.now();
      if (now - lastPreventCloseAtRef.current >= 1500) {
        lastPreventCloseAtRef.current = now;
        onPreventClose?.();
      }
      return;
    }
    onClose();
  }, [onClose, onPreventClose, preventClose]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ name, aliases, domain, industry, description, visibilityScope });
  };

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleRequestClose();
    }
  }, [handleRequestClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      className={modalScrimClassName('z-50 flex items-center justify-center p-4')}
      onClick={handleRequestClose}
    >
      <div
        className="rounded-xl w-full max-w-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            {isEdit ? '编辑品牌' : '新建品牌'}
          </h2>
          <button
            onClick={handleRequestClose}
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
                border: '1px solid var(--border-subtle)',
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
                border: '1px solid var(--border-subtle)',
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
                border: '1px solid var(--border-subtle)',
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
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
              placeholder="简要描述品牌信息..."
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
              归属空间
            </label>
            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setVisibilityScope('personal')}
                className="rounded-xl border px-4 py-3 text-left transition-colors"
                style={{
                  borderColor: visibilityScope === 'personal' ? 'var(--color-primary)' : 'var(--border-subtle)',
                  backgroundColor: visibilityScope === 'personal' ? 'color-mix(in srgb, var(--color-primary) 10%, var(--bg-primary) 90%)' : 'var(--bg-primary)',
                }}
              >
                <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  个人空间
                </div>
                <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                  仅你自己可见，适合个人试验和私有采集。
                </div>
              </button>
              <button
                type="button"
                onClick={() => {
                  if (allowOrganizationScope) {
                    setVisibilityScope('organization');
                  }
                }}
                disabled={!allowOrganizationScope}
                className="rounded-xl border px-4 py-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60"
                style={{
                  borderColor: visibilityScope === 'organization' ? 'var(--color-primary)' : 'var(--border-subtle)',
                  backgroundColor: visibilityScope === 'organization' ? 'color-mix(in srgb, var(--color-primary) 10%, var(--bg-primary) 90%)' : 'var(--bg-primary)',
                }}
              >
                <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  组织空间
                </div>
                <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                  同组织账号可共享查看品牌历史采集和分析结果。
                </div>
                {!allowOrganizationScope && (
                  <div className="mt-2 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                    账号加入组织后才可使用。
                  </div>
                )}
              </button>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleRequestClose}
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
