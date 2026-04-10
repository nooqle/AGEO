import { create } from 'zustand';
import { BrowserCanvasContent, CanvasContent, CanvasMode, ContentVersion } from '@/types/canvas';

const MAX_VERSIONS = 10;
const MERGED_ITEM_ARRAY_KEYS = new Set(['auto_items', 'manual_items']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function mergeItemsById(existing: unknown, incoming: unknown): unknown {
  if (!Array.isArray(incoming)) {
    return existing;
  }
  if (!Array.isArray(existing)) {
    return incoming;
  }

  const merged = new Map<string, Record<string, unknown>>();

  for (const item of existing) {
    if (!isRecord(item)) {
      continue;
    }
    const itemId = typeof item.item_id === 'string' ? item.item_id : null;
    if (!itemId) {
      continue;
    }
    merged.set(itemId, item);
  }

  for (const item of incoming) {
    if (!isRecord(item)) {
      continue;
    }
    const itemId = typeof item.item_id === 'string' ? item.item_id : null;
    if (!itemId) {
      continue;
    }
    const previous = merged.get(itemId) ?? {};
    merged.set(itemId, { ...previous, ...item });
  }

  return Array.from(merged.values());
}

function mergeCanvasData(
  currentData: CanvasContent['data'],
  patchData: Partial<CanvasContent['data']>
): CanvasContent['data'] {
  const merged: Record<string, unknown> = {
    ...(currentData as Record<string, unknown>),
    ...(patchData as Record<string, unknown>),
  };

  for (const key of Object.keys(patchData as Record<string, unknown>)) {
    const nextValue = (patchData as Record<string, unknown>)[key];
    const previousValue = (currentData as Record<string, unknown>)[key];

    if (MERGED_ITEM_ARRAY_KEYS.has(key)) {
      merged[key] = mergeItemsById(previousValue, nextValue);
      continue;
    }

    if (isRecord(previousValue) && isRecord(nextValue)) {
      merged[key] = { ...previousValue, ...nextValue };
    }
  }

  return merged as CanvasContent['data'];
}

function shouldPreserveArtifactFocus(
  state: Pick<CanvasState, 'isOpen' | 'contents' | 'activeContentIndex' | 'activeSurface'>,
): boolean {
  return state.isOpen && state.activeSurface === 'browser';
}

function buildBrowserWorkspaceRegistration(
  state: Pick<CanvasState, 'browserWorkspace' | 'isOpen' | 'mode' | 'activeSurface'>,
  content: BrowserCanvasContent,
) {
  return {
    browserWorkspace: content,
    isOpen: state.isOpen,
    mode: state.mode,
    activeSurface:
      state.activeSurface === 'browser' && state.isOpen ? 'browser' : state.activeSurface,
  } as const;
}

function getBrowserWorkspaceSyncKey(content: BrowserCanvasContent | null): string {
  if (!content) {
    return '';
  }

  const browserState = content.data.browserState;
  const takeover = browserState.takeover;

  return JSON.stringify({
    takeoverId: content.data.takeoverId,
    platform: content.data.platform,
    mode: content.data.mode,
    targetUrl: content.data.targetUrl,
    description: content.data.description,
    state: browserState.state,
    message: browserState.message,
    actionHint: browserState.actionHint,
    actionType: browserState.actionType,
    requiresAction: browserState.requiresAction,
    progress: browserState.progress,
    requestId: browserState.requestId,
    relatedMessageId: browserState.relatedMessageId,
    takeoverExpiresAt: takeover?.expiresAt,
    takeoverTargetUrl: takeover?.targetUrl,
  });
}

interface CanvasState {
  isOpen: boolean;
  mode: CanvasMode;
  contents: CanvasContent[];
  browserWorkspace: BrowserCanvasContent | null;
  activeContentIndex: number;
  activeSurface: 'artifact' | 'browser';

  // Actions
  openCanvas: (content?: CanvasContent) => void;
  openBrowserWorkspace: (content: BrowserCanvasContent) => void;
  closeCanvas: () => void;
  setMode: (mode: CanvasMode) => void;
  addContent: (content: CanvasContent) => void;
  upsertContent: (content: CanvasContent) => void;
  updateBrowserWorkspace: (content: BrowserCanvasContent) => void;
  clearBrowserWorkspace: () => void;
  setActiveSurface: (surface: 'artifact' | 'browser') => void;
  setActiveContent: (index: number) => void;
  setActiveContentById: (id: string) => void;
  removeContent: (id: string) => void;
  removeContentsByIds: (ids: string[]) => void;
  updateContent: (id: string, data: Partial<CanvasContent['data']>) => void;
  patchContent: (id: string, patch: Partial<CanvasContent['data']>) => void;
  setOpen: (open: boolean) => void;
  clearContents: () => void;
  setContentVersion: (id: string, versionIndex: number) => void;
}

export const useCanvasStore = create<CanvasState>((set) => ({
  isOpen: false,
  mode: 'hidden',
  contents: [],
  browserWorkspace: null,
  activeContentIndex: 0,
  activeSurface: 'artifact',

  openCanvas: (content) => set((state) => {
    const newState: Partial<CanvasState> = {
      isOpen: true,
      mode: 'split',
    };
    if (content) {
      const existingIndex = state.contents.findIndex((c) => c.id === content.id);
      if (existingIndex === -1) {
        newState.contents = [...state.contents, content];
        newState.activeContentIndex = state.contents.length;
      } else {
        newState.activeContentIndex = existingIndex;
      }
      newState.activeSurface = content.type === 'browser' ? 'browser' : 'artifact';
      if (content.type === 'browser') {
        newState.browserWorkspace = content as BrowserCanvasContent;
        return newState;
      }
    } else if (state.browserWorkspace && state.contents.length === 0) {
      newState.activeSurface = 'browser';
    } else if (state.contents.length > 0) {
      newState.activeSurface = 'artifact';
    }
    return newState;
  }),

  openBrowserWorkspace: (content) =>
    set((state) => ({
      browserWorkspace: content,
      isOpen: true,
      mode: state.mode === 'hidden' ? 'split' : state.mode,
      activeSurface: 'browser',
    })),

  closeCanvas: () => set({ isOpen: false, mode: 'hidden' }),

  setMode: (mode) => set({ mode, isOpen: mode !== 'hidden' }),

  addContent: (content) => set((state) => {
    if (content.type === 'browser') {
      return buildBrowserWorkspaceRegistration(state, content as BrowserCanvasContent);
    }
    const existingIndex = state.contents.findIndex((c) => c.id === content.id);
    if (existingIndex !== -1) {
      // Same ID exists — merge as new version
      const existing = state.contents[existingIndex];
      const oldVersion: ContentVersion = {
        versionNumber: (existing.versions?.length ?? 0) + 1,
        timestamp: existing.createdAt?.toISOString?.() || new Date().toISOString(),
        data: existing.data as Record<string, unknown>,
        linkedMessageId: existing.linkedMessageId,
      };
      // Prepend old version (newest-first order), cap at MAX_VERSIONS
      const updatedVersions = [oldVersion, ...(existing.versions || [])].slice(0, MAX_VERSIONS);
      const newContents = [...state.contents];
      // If user is currently viewing this tab, no need to show NEW badge
      const isCurrentlyViewing = existingIndex === state.activeContentIndex;
      newContents[existingIndex] = {
        ...existing,
        ...content,
        versions: updatedVersions,
        currentVersionIndex: -1, // -1 = show latest
        hasNewVersion: !isCurrentlyViewing,
      } as CanvasContent;
      return {
        contents: newContents,
        activeContentIndex: shouldPreserveArtifactFocus(state)
          ? state.activeContentIndex
          : existingIndex,
        isOpen: true,
        mode: state.mode === 'hidden' ? 'split' : state.mode,
        activeSurface: shouldPreserveArtifactFocus(state)
          ? state.activeSurface
          : 'artifact',
      };
    }
    // New content — ensure version fields are initialized
    const newContent = {
      ...content,
      versions: content.versions || [],
      currentVersionIndex: content.currentVersionIndex ?? -1,
    } as CanvasContent;
    return {
      contents: [...state.contents, newContent],
      activeContentIndex: shouldPreserveArtifactFocus(state)
        ? state.activeContentIndex
        : state.contents.length,
      isOpen: true,
      mode: state.mode === 'hidden' ? 'split' : state.mode,
      activeSurface: shouldPreserveArtifactFocus(state)
        ? state.activeSurface
        : 'artifact',
    };
  }),

  upsertContent: (content) => set((state) => {
    if (content.type === 'browser') {
      return buildBrowserWorkspaceRegistration(state, content as BrowserCanvasContent);
    }
    const existingIndex = state.contents.findIndex((c) => c.id === content.id);
    if (existingIndex === -1) {
      return {
        contents: [...state.contents, content],
        activeContentIndex: shouldPreserveArtifactFocus(state)
          ? state.activeContentIndex
          : state.contents.length,
        isOpen: true,
        mode: state.mode === 'hidden' ? 'split' : state.mode,
        activeSurface: shouldPreserveArtifactFocus(state)
          ? state.activeSurface
          : 'artifact',
      };
    }

    const nextContents = [...state.contents];
    nextContents[existingIndex] = content;
    return {
      contents: nextContents,
      isOpen: state.isOpen,
      mode: state.mode,
    };
  }),

  updateBrowserWorkspace: (content) =>
    set((state) => {
      const currentKey = getBrowserWorkspaceSyncKey(state.browserWorkspace);
      const nextKey = getBrowserWorkspaceSyncKey(content);

      if (currentKey && currentKey === nextKey) {
        return state;
      }

      return {
        browserWorkspace: content,
        isOpen: true,
        mode: state.mode === 'hidden' ? 'split' : state.mode,
        activeSurface: state.isOpen ? state.activeSurface : 'browser',
      };
    }),

  clearBrowserWorkspace: () =>
    set((state) => {
      const hasArtifacts = state.contents.length > 0;
      return {
        browserWorkspace: null,
        activeSurface: 'artifact',
        isOpen: hasArtifacts ? state.isOpen : false,
        mode: hasArtifacts ? state.mode : 'hidden',
      };
    }),

  setActiveSurface: (surface) =>
    set((state) => {
      if (surface === 'browser' && !state.browserWorkspace) {
        return {};
      }
      if (surface === 'artifact' && state.contents.length === 0) {
        return state.browserWorkspace ? { activeSurface: 'browser' } : {};
      }
      return {
        activeSurface: surface,
        isOpen: true,
        mode: state.mode === 'hidden' ? 'split' : state.mode,
      };
    }),

  setActiveContent: (index) => set((state) => {
    const newContents = [...state.contents];
    if (newContents[index]) {
      newContents[index] = { ...newContents[index], hasNewVersion: false } as CanvasContent;
    }
    return { activeContentIndex: index, contents: newContents, activeSurface: 'artifact' };
  }),

  setActiveContentById: (id) => set((state) => {
    const index = state.contents.findIndex((c) => c.id === id);
    return index !== -1 ? { activeContentIndex: index, activeSurface: 'artifact' } : {};
  }),

  removeContent: (id) => set((state) => {
    if (state.browserWorkspace?.id === id) {
      const hasArtifacts = state.contents.length > 0;
      return {
        browserWorkspace: null,
        activeSurface: 'artifact',
        isOpen: hasArtifacts ? state.isOpen : false,
        mode: hasArtifacts ? state.mode : 'hidden',
      };
    }
    const newContents = state.contents.filter((c) => c.id !== id);
    const newIndex = Math.min(state.activeContentIndex, Math.max(0, newContents.length - 1));
    const nextHasSurface = newContents.length > 0 || Boolean(state.browserWorkspace);
    return {
      contents: newContents,
      activeContentIndex: newIndex,
      isOpen: nextHasSurface ? state.isOpen : false,
      mode: nextHasSurface ? state.mode : 'hidden',
      activeSurface:
        newContents.length > 0
          ? state.activeSurface
          : state.browserWorkspace
            ? 'browser'
            : 'artifact',
    };
  }),

  removeContentsByIds: (ids) => set((state) => {
    const idsSet = new Set(ids);
    const newContents = state.contents.filter((c) => !idsSet.has(c.id));
    const newIndex = Math.min(state.activeContentIndex, Math.max(0, newContents.length - 1));
    const nextHasSurface = newContents.length > 0 || Boolean(state.browserWorkspace);
    return {
      contents: newContents,
      activeContentIndex: newIndex,
      isOpen: nextHasSurface ? state.isOpen : false,
      mode: nextHasSurface ? state.mode : 'hidden',
      activeSurface:
        newContents.length > 0
          ? state.activeSurface
          : state.browserWorkspace
            ? 'browser'
            : 'artifact',
    };
  }),

  updateContent: (id, data) => set((state) => ({
    contents: state.contents.map((c) =>
      c.id === id ? { ...c, data: { ...c.data, ...data } } as CanvasContent : c
    ),
  })),

  patchContent: (id, patch) => set((state) => ({
    contents: state.contents.map((content) =>
      content.id === id
        ? {
            ...content,
            data: mergeCanvasData(content.data, patch),
          } as CanvasContent
        : content
    ),
  })),

  setOpen: (open) => set({ isOpen: open, mode: open ? 'split' : 'hidden' }),

  clearContents: () => set({
    contents: [],
    browserWorkspace: null,
    activeContentIndex: 0,
    isOpen: false,
    mode: 'hidden',
    activeSurface: 'artifact',
  }),

  setContentVersion: (id, versionIndex) => set((state) => ({
    contents: state.contents.map((c) =>
      c.id === id ? { ...c, currentVersionIndex: versionIndex } as CanvasContent : c
    ),
  })),
}));
