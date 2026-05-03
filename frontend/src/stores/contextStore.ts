import { create } from 'zustand';

export interface ContextTag {
  id: string;
  type: 'profile' | 'scenario' | 'intent';
  label: string;
  data?: Record<string, unknown>;
}

interface ContextState {
  contextTags: ContextTag[];
  addContextTag: (tag: ContextTag) => void;
  removeContextTag: (id: string) => void;
  clearContextTags: () => void;
}

export const useContextStore = create<ContextState>((set) => ({
  contextTags: [],
  addContextTag: (tag) =>
    set((state) => {
      // Prevent duplicates
      if (state.contextTags.some((t) => t.id === tag.id)) return state;
      return { contextTags: [...state.contextTags, tag] };
    }),
  removeContextTag: (id) =>
    set((state) => ({
      contextTags: state.contextTags.filter((t) => t.id !== id),
    })),
  clearContextTags: () => set({ contextTags: [] }),
}));
