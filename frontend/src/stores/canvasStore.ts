import { create } from 'zustand';
import { CanvasContent, CanvasMode, ContentVersion } from '@/types/canvas';

const MAX_VERSIONS = 10;

interface CanvasState {
  isOpen: boolean;
  mode: CanvasMode;
  contents: CanvasContent[];
  activeContentIndex: number;

  // Actions
  openCanvas: (content?: CanvasContent) => void;
  closeCanvas: () => void;
  setMode: (mode: CanvasMode) => void;
  addContent: (content: CanvasContent) => void;
  setActiveContent: (index: number) => void;
  setActiveContentById: (id: string) => void;
  removeContent: (id: string) => void;
  removeContentsByIds: (ids: string[]) => void;
  updateContent: (id: string, data: Partial<CanvasContent['data']>) => void;
  setOpen: (open: boolean) => void;
  clearContents: () => void;
  setContentVersion: (id: string, versionIndex: number) => void;
}

export const useCanvasStore = create<CanvasState>((set) => ({
  isOpen: false,
  mode: 'hidden',
  contents: [],
  activeContentIndex: 0,

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
    }
    return newState;
  }),

  closeCanvas: () => set({ isOpen: false, mode: 'hidden' }),

  setMode: (mode) => set({ mode, isOpen: mode !== 'hidden' }),

  addContent: (content) => set((state) => {
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
        activeContentIndex: existingIndex,
        isOpen: true,
        mode: state.mode === 'hidden' ? 'split' : state.mode,
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
      activeContentIndex: state.contents.length,
      isOpen: true,
      mode: state.mode === 'hidden' ? 'split' : state.mode,
    };
  }),

  setActiveContent: (index) => set((state) => {
    const newContents = [...state.contents];
    if (newContents[index]) {
      newContents[index] = { ...newContents[index], hasNewVersion: false } as CanvasContent;
    }
    return { activeContentIndex: index, contents: newContents };
  }),

  setActiveContentById: (id) => set((state) => {
    const index = state.contents.findIndex((c) => c.id === id);
    return index !== -1 ? { activeContentIndex: index } : {};
  }),

  removeContent: (id) => set((state) => {
    const newContents = state.contents.filter((c) => c.id !== id);
    const newIndex = Math.min(state.activeContentIndex, Math.max(0, newContents.length - 1));
    return {
      contents: newContents,
      activeContentIndex: newIndex,
      isOpen: newContents.length > 0,
      mode: newContents.length > 0 ? state.mode : 'hidden',
    };
  }),

  removeContentsByIds: (ids) => set((state) => {
    const idsSet = new Set(ids);
    const newContents = state.contents.filter((c) => !idsSet.has(c.id));
    const newIndex = Math.min(state.activeContentIndex, Math.max(0, newContents.length - 1));
    return {
      contents: newContents,
      activeContentIndex: newIndex,
      isOpen: newContents.length > 0,
      mode: newContents.length > 0 ? state.mode : 'hidden',
    };
  }),

  updateContent: (id, data) => set((state) => ({
    contents: state.contents.map((c) =>
      c.id === id ? { ...c, data: { ...c.data, ...data } } as CanvasContent : c
    ),
  })),

  setOpen: (open) => set({ isOpen: open, mode: open ? 'split' : 'hidden' }),

  clearContents: () => set({
    contents: [],
    activeContentIndex: 0,
    isOpen: false,
    mode: 'hidden',
  }),

  setContentVersion: (id, versionIndex) => set((state) => ({
    contents: state.contents.map((c) =>
      c.id === id ? { ...c, currentVersionIndex: versionIndex } as CanvasContent : c
    ),
  })),
}));
