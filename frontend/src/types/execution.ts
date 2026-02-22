export interface StopState {
  isStopped: boolean;
  completedStages: {
    name: string;
    description?: string;
  }[];
  pendingStages: {
    name: string;
    description?: string;
  }[];
  partialResults?: {
    fetchedCount: number;
    totalCount: number;
  };
}

export interface RollbackInfo {
  messagesToDelete: number;
  outputsToDelete: {
    id: string;
    type: string;
    title: string;
  }[];
  dataToDelete?: {
    fetchResultsCount: number;
    questionsCount: number;
  };
  tasksToDelete?: {
    name: string;
    schedule: string;
  }[];
}
