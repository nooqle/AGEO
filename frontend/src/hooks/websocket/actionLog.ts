import type { ActionLogEntry, Message } from '@/types/message';

export function normalizeActionLogText(value: string): string {
  return value
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/^调用\s+/, '')
    .replace(/^完成[：:]?\s*/, '')
    .replace(/^已完成[：:]?\s*/, '')
    .replace(/^正在执行[：:]?\s*/, '')
    .replace(/(?:\.\.\.|…)+$/g, '')
    .replace(/\s*内容生成完成$/, '')
    .replace(/\s*完成$/, '')
    .trim();
}

export function findMatchingPendingActionLog(
  logs: ActionLogEntry[],
  params: { actionType: string; message: string; step: string; isComplete: boolean }
): ActionLogEntry | null {
  const pendingLogs = logs.filter((log) => !log.isComplete);
  if (pendingLogs.length === 0) {
    return null;
  }

  const { actionType, message, step, isComplete } = params;
  const normalizedMessage = normalizeActionLogText(message);

  if (step) {
    const exactStepMatch = pendingLogs.find((log) => log.step === step);
    if (exactStepMatch) {
      return exactStepMatch;
    }
  }

  if (normalizedMessage) {
    const exactMessageMatch = pendingLogs.find(
      (log) => normalizeActionLogText(log.message) === normalizedMessage
    );
    if (exactMessageMatch) {
      return exactMessageMatch;
    }

    const fuzzyMessageMatch = [...pendingLogs].reverse().find((log) => {
      const existing = normalizeActionLogText(log.message);
      return existing && (existing.includes(normalizedMessage) || normalizedMessage.includes(existing));
    });
    if (fuzzyMessageMatch) {
      return fuzzyMessageMatch;
    }
  }

  if (isComplete) {
    const sameTypeMatch = [...pendingLogs].reverse().find((log) => log.actionType === actionType);
    if (sameTypeMatch) {
      return sameTypeMatch;
    }

    return pendingLogs[pendingLogs.length - 1] || null;
  }

  return null;
}

export function collectPendingActionLogs(
  currentLogs: ActionLogEntry[],
  messages: Message[]
): ActionLogEntry[] {
  const seen = new Set<string>();
  const collected: ActionLogEntry[] = [];

  const pushLogs = (logs: ActionLogEntry[]) => {
    for (const log of logs) {
      if (log.isComplete || seen.has(log.id)) {
        continue;
      }
      seen.add(log.id);
      collected.push(log);
    }
  };

  pushLogs(currentLogs);

  [...messages]
    .reverse()
    .filter((message) => message.type === 'agent')
    .forEach((message) => {
      pushLogs(message.layers?.actionLogs || []);
    });

  return collected;
}
