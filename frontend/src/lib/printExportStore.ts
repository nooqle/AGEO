import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import type { CanvasContent } from '@/types/canvas';
import type { ExportDescriptor } from '@/lib/canvasExportShared';

type PrintExportPayload = {
  content: CanvasContent;
  descriptor: ExportDescriptor;
};

type PrintExportEntry = {
  payload: PrintExportPayload;
  expiresAt: number;
};

const STORE_DIR = path.join(os.tmpdir(), 'specta-print-export');
const TTL_MS = 5 * 60 * 1000;

function ensureStoreDir() {
  if (!fs.existsSync(STORE_DIR)) {
    fs.mkdirSync(STORE_DIR, { recursive: true });
  }
}

function isSafeId(value: string): boolean {
  return /^[a-z0-9-]+$/i.test(value);
}

function getEntryPath(id: string): string | null {
  if (!isSafeId(id)) {
    return null;
  }
  ensureStoreDir();
  return path.join(STORE_DIR, `${id}.json`);
}

function pruneExpiredEntries() {
  ensureStoreDir();
  const now = Date.now();
  for (const file of fs.readdirSync(STORE_DIR)) {
    if (!file.endsWith('.json')) {
      continue;
    }

    const filePath = path.join(STORE_DIR, file);
    try {
      const raw = fs.readFileSync(filePath, 'utf8');
      const entry = JSON.parse(raw) as Partial<PrintExportEntry>;
      if (typeof entry.expiresAt !== 'number' || entry.expiresAt <= now) {
        fs.rmSync(filePath, { force: true });
      }
    } catch {
      fs.rmSync(filePath, { force: true });
    }
  }
}

export function createPrintExportEntry(payload: PrintExportPayload): string {
  pruneExpiredEntries();

  const id = randomUUID();
  const entryPath = getEntryPath(id);
  if (!entryPath) {
    throw new Error('生成导出 ID 失败');
  }

  const entry: PrintExportEntry = {
    payload,
    expiresAt: Date.now() + TTL_MS,
  };
  fs.writeFileSync(entryPath, JSON.stringify(entry), 'utf8');

  return id;
}

export function getPrintExportEntry(id: string): PrintExportPayload | null {
  pruneExpiredEntries();
  const entryPath = getEntryPath(id);
  if (!entryPath || !fs.existsSync(entryPath)) {
    return null;
  }

  try {
    const raw = fs.readFileSync(entryPath, 'utf8');
    const entry = JSON.parse(raw) as Partial<PrintExportEntry>;
    if (
      typeof entry.expiresAt !== 'number' ||
      entry.expiresAt <= Date.now() ||
      !entry.payload
    ) {
      fs.rmSync(entryPath, { force: true });
      return null;
    }

    return entry.payload;
  } catch {
    fs.rmSync(entryPath, { force: true });
    return null;
  }
}

export function deletePrintExportEntry(id: string) {
  const entryPath = getEntryPath(id);
  if (!entryPath) {
    return;
  }
  fs.rmSync(entryPath, { force: true });
}
