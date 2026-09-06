import { useState } from 'react';
import { api } from '@/services/api';
import { lexiconStatusLabels, semanticTypeLabels } from './amwaySemanticLabels';

type Preview = Awaited<ReturnType<typeof api.previewAmwayLexiconRepair>>;

function downloadJson(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export function AmwayLexiconRepairControls({ entityId, onApplied }: { entityId: string; onApplied: () => Promise<void> }) {
  const [packageData, setPackageData] = useState<Record<string, unknown> | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [pendingHash, setPendingHash] = useState<string | null>(null);
  const entryNames = new Map(preview?.entries.map((entry) => [entry.entity_id, entry.canonical_name]) || []);
  const buttonClass = 'rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm disabled:opacity-50';

  const exportBackup = async () => {
    setBusy(true);
    try {
      downloadJson(await api.exportAmwayLexiconRepair(entityId), `lexicon-backup-${entityId}.json`);
      setPendingHash(null);
      setPreview(null);
      setPackageData(null);
      setMessage('已导出当前词库及覆盖行前像，请保留备份。');
    } catch (error) { setMessage(error instanceof Error ? error.message : '导出失败'); }
    finally { setBusy(false); }
  };
  const readPackage = async (file?: File) => {
    setPreview(null);
    setPackageData(null);
    if (!file) return;
    setBusy(true);
    try {
      const data = JSON.parse(await file.text()) as Record<string, unknown>;
      const result = await api.previewAmwayLexiconRepair(entityId, data);
      setPackageData(data);
      setPreview(result);
      setMessage(`预览通过：71 条来源记录已覆盖，${result.changed_ids.length} 项增改。尚未应用。`);
    } catch (error) { setMessage(error instanceof Error ? error.message : '预览失败'); }
    finally { setBusy(false); }
  };
  const apply = async () => {
    if (!packageData || !preview || pendingHash) return;
    setBusy(true);
    setPendingHash(preview.effective_hash);
    let writeConfirmed = false;
    try {
      downloadJson(preview.before_image, `lexicon-before-apply-${entityId}.json`);
      const result = await api.previewAmwayLexiconRepair(entityId, packageData, true);
      writeConfirmed = true;
      const readback = await api.getAmwayEntityLexicon(entityId);
      if (readback.effective_hash !== result.effective_hash) throw new Error('应用后的词库版本与预期不同，请保留备份并停止操作。');
      setMessage(`已${result.status === 'unchanged' ? '确认无需重复修改' : '应用并回读验证'}，${result.changed_ids.length} 项增改。`);
      setPreview(null);
      setPackageData(null);
      setPendingHash(null);
      await onApplied();
    } catch (error) {
      setPreview(null);
      setPackageData(null);
      setMessage(`${writeConfirmed ? '写入已完成，回读尚未确认' : '应用未确认（可能版本冲突或响应中断）'}：${error instanceof Error ? error.message : '请重读或重新导出备份'}。已关闭重复应用。`);
    }
    finally { setBusy(false); }
  };
  const verifyPending = async () => {
    setBusy(true);
    try {
      const current = await api.getAmwayEntityLexicon(entityId);
      if (current.effective_hash !== pendingHash) throw new Error('当前版本与预期不同，请重新导出并审核');
      setPendingHash(null);
      setMessage('已重新读取并确认目标词库版本。');
      await onApplied();
    } catch (error) { setMessage(error instanceof Error ? error.message : '回读失败'); }
    finally { setBusy(false); }
  };

  return <div className="space-y-2 border-b border-[var(--border-subtle)] pb-4">
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" disabled={busy} className={buttonClass} onClick={() => void exportBackup()}>导出词库备份</button>
      <label className={buttonClass}>预览合并清单
        <input aria-label="导入审核后的实体合并 JSON" type="file" accept=".json,application/json" disabled={busy || Boolean(pendingHash)}
          className="ml-2 max-w-52 text-xs" onChange={(event) => { void readPackage(event.target.files?.[0]); event.target.value = ''; }} />
      </label>
      {preview && <button type="button" disabled={busy} onClick={() => void apply()}
        className="rounded-lg bg-[var(--brand-primary)] px-3 py-2 text-sm text-[var(--brand-contrast)] disabled:opacity-50">应用已预览的合并清单</button>}
      {pendingHash && <button type="button" disabled={busy} className={buttonClass} onClick={() => void verifyPending()}>重新读取确认</button>}
    </div>
    {preview && <details className="text-sm"><summary>查看 {preview.changed_ids.length} 项增改及版本</summary>
      <p className="break-all">当前：{preview.before_hash}<br />应用后：{preview.effective_hash}</p>
      <details><summary>查看记录 ID</summary><p className="break-words">{preview.changed_ids.join('、') || '无需修改'}</p></details>
      <p>新增 {preview.changes.filter((item) => !item.before).length} 项，修改 {preview.changes.filter((item) => item.before).length} 项。</p>
      <div className="max-h-80 overflow-y-auto divide-y divide-[var(--border-subtle)]">
        {preview.changes.map((item) => <div key={item.entity_id} className="py-2">
          <p>{item.before?.canonical_name || '新增'} → {item.after.canonical_name}</p>
          <p>同义名称：{item.before?.aliases.join('、') || '无'} → {item.after.aliases.join('、') || '无'}</p>
          <p>对象类型：{semanticTypeLabels[item.before?.semantic_definition?.semantic_type || ''] || '旧版未区分'} → {semanticTypeLabels[item.after.semantic_definition?.semantic_type || ''] || '旧版未区分'}</p>
          <p>主题归属：{item.before?.semantic_definition?.topic_mappings.map((mapping) => entryNames.get(mapping.target_entity_id) || mapping.target_entity_id).join('、') || '无'} → {item.after.semantic_definition?.topic_mappings.map((mapping) => entryNames.get(mapping.target_entity_id) || mapping.target_entity_id).join('、') || '无'}</p>
          <p>状态：{lexiconStatusLabels[item.before?.review_status || ''] || '新增'} → {lexiconStatusLabels[item.after.review_status]}</p>
        </div>)}
      </div>
    </details>}
    <p role="status" className="text-sm text-[var(--text-secondary)]">{message || '仅管理者可导出或应用；预览不会修改词库。'}</p>
  </div>;
}
