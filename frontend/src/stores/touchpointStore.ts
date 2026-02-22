import { create } from 'zustand';
import type { TouchpointTree } from '@/types/touchpoint';

interface TouchpointState {
  tree: TouchpointTree | null;
  selectedNodeId: string | null;
  isLoading: boolean;
  error: string | null;

  setTree: (tree: TouchpointTree) => void;
  setSelectedNodeId: (id: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useTouchpointStore = create<TouchpointState>((set) => ({
  tree: null,
  selectedNodeId: null,
  isLoading: false,
  error: null,

  setTree: (tree) => set({ tree, isLoading: false }),
  setSelectedNodeId: (selectedNodeId) => set({ selectedNodeId }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error, isLoading: false }),
  reset: () =>
    set({
      tree: null,
      selectedNodeId: null,
      isLoading: false,
      error: null,
    }),
}));
