import { create } from 'zustand';

import { api } from '@/services/api';
import type {
  OntologyActionFeedbackType,
  OntologyFindingFeedbackType,
  OntologyObjectCollection,
  OntologyRecommendationTaskRequest,
  OntologyWorldSummary,
} from '@/types/ontology';

interface OntologyState {
  worldsByEntity: Record<string, OntologyWorldSummary>;
  objectCollectionsByKey: Record<string, OntologyObjectCollection>;
  loadingByEntity: Record<string, boolean>;
  collectionLoadingByKey: Record<string, boolean>;
  errorByEntity: Record<string, string | null>;
  collectionErrorByKey: Record<string, string | null>;
  actionFeedbackSubmittingByKey: Record<string, boolean>;
  actionFeedbackErrorByKey: Record<string, string | null>;
  feedbackSubmittingByFinding: Record<string, boolean>;
  feedbackErrorByFinding: Record<string, string | null>;
  recommendationTaskSubmittingByKey: Record<string, boolean>;
  recommendationTaskErrorByKey: Record<string, string | null>;
  activeRequestByEntity: Record<string, number>;
  fetchWorld: (entityId: string) => Promise<void>;
  fetchObjectCollection: (
    entityId: string,
    objectType: string,
    options?: { limit?: number; offset?: number; sort?: string; status?: string },
  ) => Promise<void>;
  submitActionFeedback: (
    entityId: string,
    actionKey: string,
    feedbackType: OntologyActionFeedbackType,
    feedbackText?: string,
    providedInputs?: Record<string, unknown>,
  ) => Promise<void>;
  submitFindingFeedback: (
    entityId: string,
    findingId: string,
    feedbackType: OntologyFindingFeedbackType,
    feedbackText?: string,
  ) => Promise<void>;
  submitRecommendationTask: (
    entityId: string,
    recommendationId: string,
    payload: OntologyRecommendationTaskRequest,
  ) => Promise<void>;
  reset: () => void;
}

export const useOntologyStore = create<OntologyState>((set, get) => ({
  worldsByEntity: {},
  objectCollectionsByKey: {},
  loadingByEntity: {},
  collectionLoadingByKey: {},
  errorByEntity: {},
  collectionErrorByKey: {},
  actionFeedbackSubmittingByKey: {},
  actionFeedbackErrorByKey: {},
  feedbackSubmittingByFinding: {},
  feedbackErrorByFinding: {},
  recommendationTaskSubmittingByKey: {},
  recommendationTaskErrorByKey: {},
  activeRequestByEntity: {},

  fetchWorld: async (entityId: string) => {
    const requestId = (get().activeRequestByEntity[entityId] ?? 0) + 1;
    set((state) => ({
      loadingByEntity: { ...state.loadingByEntity, [entityId]: true },
      errorByEntity: { ...state.errorByEntity, [entityId]: null },
      activeRequestByEntity: {
        ...state.activeRequestByEntity,
        [entityId]: requestId,
      },
    }));

    try {
      const world = await api.getOntologyWorld(entityId);
      const latest = get();
      if (latest.activeRequestByEntity[entityId] !== requestId) return;
      set((state) => ({
        worldsByEntity: { ...state.worldsByEntity, [entityId]: world },
        loadingByEntity: { ...state.loadingByEntity, [entityId]: false },
        errorByEntity: { ...state.errorByEntity, [entityId]: null },
      }));
    } catch (error) {
      const latest = get();
      if (latest.activeRequestByEntity[entityId] !== requestId) return;
      set((state) => ({
        loadingByEntity: { ...state.loadingByEntity, [entityId]: false },
        errorByEntity: {
          ...state.errorByEntity,
          [entityId]: error instanceof Error ? error.message : '品牌情报加载失败',
        },
      }));
    }
  },

  fetchObjectCollection: async (entityId, objectType, options) => {
    const key = collectionKey(entityId, objectType);
    set((state) => ({
      collectionLoadingByKey: { ...state.collectionLoadingByKey, [key]: true },
      collectionErrorByKey: { ...state.collectionErrorByKey, [key]: null },
    }));

    try {
      const collection = await api.listOntologyObjects(entityId, objectType, {
        limit: options?.limit ?? 4,
        offset: options?.offset ?? 0,
        sort: options?.sort ?? 'updated_at_desc',
        status: options?.status,
      });
      set((state) => ({
        objectCollectionsByKey: {
          ...state.objectCollectionsByKey,
          [key]: collection,
        },
        collectionLoadingByKey: {
          ...state.collectionLoadingByKey,
          [key]: false,
        },
        collectionErrorByKey: {
          ...state.collectionErrorByKey,
          [key]: null,
        },
      }));
    } catch (error) {
      set((state) => ({
        collectionLoadingByKey: {
          ...state.collectionLoadingByKey,
          [key]: false,
        },
        collectionErrorByKey: {
          ...state.collectionErrorByKey,
          [key]: error instanceof Error ? error.message : '资料明细加载失败',
        },
      }));
    }
  },

  submitActionFeedback: async (
    entityId,
    actionKey,
    feedbackType,
    feedbackText,
    providedInputs,
  ) => {
    const key = `${entityId}:${actionKey}`;
    set((state) => ({
      actionFeedbackSubmittingByKey: {
        ...state.actionFeedbackSubmittingByKey,
        [key]: true,
      },
      actionFeedbackErrorByKey: {
        ...state.actionFeedbackErrorByKey,
        [key]: null,
      },
    }));

    try {
      const response = await api.submitOntologyActionFeedback(entityId, actionKey, {
        feedback_type: feedbackType,
        feedback_text: feedbackText,
        provided_inputs: providedInputs,
      });
      set((state) => ({
        worldsByEntity: {
          ...state.worldsByEntity,
          [entityId]: response.world,
        },
        actionFeedbackSubmittingByKey: {
          ...state.actionFeedbackSubmittingByKey,
          [key]: false,
        },
        actionFeedbackErrorByKey: {
          ...state.actionFeedbackErrorByKey,
          [key]: null,
        },
      }));
    } catch (error) {
      set((state) => ({
        actionFeedbackSubmittingByKey: {
          ...state.actionFeedbackSubmittingByKey,
          [key]: false,
        },
        actionFeedbackErrorByKey: {
          ...state.actionFeedbackErrorByKey,
          [key]: error instanceof Error ? error.message : '行动反馈提交失败',
        },
      }));
    }
  },

  submitFindingFeedback: async (entityId, findingId, feedbackType, feedbackText) => {
    set((state) => ({
      feedbackSubmittingByFinding: {
        ...state.feedbackSubmittingByFinding,
        [findingId]: true,
      },
      feedbackErrorByFinding: {
        ...state.feedbackErrorByFinding,
        [findingId]: null,
      },
    }));

    try {
      const response = await api.submitOntologyFindingFeedback(entityId, findingId, {
        feedback_type: feedbackType,
        feedback_text: feedbackText,
      });
      set((state) => ({
        worldsByEntity: {
          ...state.worldsByEntity,
          [entityId]: response.world,
        },
        feedbackSubmittingByFinding: {
          ...state.feedbackSubmittingByFinding,
          [findingId]: false,
        },
        feedbackErrorByFinding: {
          ...state.feedbackErrorByFinding,
          [findingId]: null,
        },
      }));
    } catch (error) {
      set((state) => ({
        feedbackSubmittingByFinding: {
          ...state.feedbackSubmittingByFinding,
          [findingId]: false,
        },
        feedbackErrorByFinding: {
          ...state.feedbackErrorByFinding,
          [findingId]: error instanceof Error ? error.message : '反馈提交失败',
        },
      }));
    }
  },

  submitRecommendationTask: async (entityId, recommendationId, payload) => {
    const key = `${entityId}:${recommendationId}`;
    set((state) => ({
      recommendationTaskSubmittingByKey: {
        ...state.recommendationTaskSubmittingByKey,
        [key]: true,
      },
      recommendationTaskErrorByKey: {
        ...state.recommendationTaskErrorByKey,
        [key]: null,
      },
    }));

    try {
      const response = await api.submitOntologyRecommendationTask(
        entityId,
        recommendationId,
        payload,
      );
      set((state) => ({
        worldsByEntity: {
          ...state.worldsByEntity,
          [entityId]: response.world,
        },
        recommendationTaskSubmittingByKey: {
          ...state.recommendationTaskSubmittingByKey,
          [key]: false,
        },
        recommendationTaskErrorByKey: {
          ...state.recommendationTaskErrorByKey,
          [key]: null,
        },
      }));
    } catch (error) {
      set((state) => ({
        recommendationTaskSubmittingByKey: {
          ...state.recommendationTaskSubmittingByKey,
          [key]: false,
        },
        recommendationTaskErrorByKey: {
          ...state.recommendationTaskErrorByKey,
          [key]: error instanceof Error ? error.message : '跟进状态保存失败',
        },
      }));
    }
  },

  reset: () =>
    set({
      worldsByEntity: {},
      objectCollectionsByKey: {},
      loadingByEntity: {},
      collectionLoadingByKey: {},
      errorByEntity: {},
      collectionErrorByKey: {},
      actionFeedbackSubmittingByKey: {},
      actionFeedbackErrorByKey: {},
      feedbackSubmittingByFinding: {},
      feedbackErrorByFinding: {},
      recommendationTaskSubmittingByKey: {},
      recommendationTaskErrorByKey: {},
      activeRequestByEntity: {},
    }),
}));

function collectionKey(entityId: string, objectType: string) {
  return `${entityId}:${objectType}`;
}
