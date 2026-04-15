import { create } from 'zustand';
import type { Entity } from '@/types/entity';
import { api } from '@/services/api';

interface EntityState {
  entities: Entity[];
  isLoading: boolean;
  error: string | null;
  hasFetched: boolean;

  setEntities: (entities: Entity[]) => void;
  addEntity: (entity: Entity) => void;
  updateEntity: (id: string, updates: Partial<Entity>) => void;
  removeEntity: (id: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  fetchEntities: () => Promise<void>;
}

function parseEntityTimestamp(value?: string | null): number {
  if (!value) return 0;
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
}

function sortEntities(entities: Entity[]): Entity[] {
  return [...entities].sort((left, right) => {
    const updatedDiff =
      parseEntityTimestamp(right.updatedAt) - parseEntityTimestamp(left.updatedAt);
    if (updatedDiff !== 0) return updatedDiff;

    const createdDiff =
      parseEntityTimestamp(right.createdAt) - parseEntityTimestamp(left.createdAt);
    if (createdDiff !== 0) return createdDiff;

    return right.id.localeCompare(left.id);
  });
}

export const useEntityStore = create<EntityState>((set) => ({
  entities: [],
  isLoading: false,
  error: null,
  hasFetched: false,

  setEntities: (entities) =>
    set({
      entities: sortEntities(entities),
      isLoading: false,
      error: null,
      hasFetched: true,
    }),
  addEntity: (entity) =>
    set((state) => ({
      entities: sortEntities([...state.entities, entity]),
      hasFetched: true,
    })),
  updateEntity: (id, updates) =>
    set((state) => ({
      entities: sortEntities(
        state.entities.map((e) => (e.id === id ? { ...e, ...updates } : e))
      ),
    })),
  removeEntity: (id) =>
    set((state) => ({
      entities: state.entities.filter((e) => e.id !== id),
    })),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error, isLoading: false }),

  fetchEntities: async () => {
    set({ isLoading: true, error: null });
    try {
      const entities = await api.listEntities();
      set({
        entities: sortEntities(entities),
        isLoading: false,
        error: null,
        hasFetched: true,
      });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : '加载品牌列表失败',
        isLoading: false,
        hasFetched: true,
      });
    }
  },
}));
