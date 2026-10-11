import { storage } from './storage';

const KEY = 'last-crash';

export type CrashRecord = { error: string; at: string; version: string };

type GlobalHandler = (error: unknown, isFatal?: boolean) => void;
type ErrorUtilsShape = { getGlobalHandler(): GlobalHandler; setGlobalHandler(handler: GlobalHandler): void };

/**
 * Remembers fatal JavaScript errors that close the app, so the next launch can offer to report
 * them. Stored only on the phone and deleted once the user reports or dismisses it.
 */
export function installCrashRecorder(format: (error: unknown) => string, version: string) {
  const errorUtils = (globalThis as { ErrorUtils?: ErrorUtilsShape }).ErrorUtils;
  if (!errorUtils) return;
  const previous = errorUtils.getGlobalHandler();
  errorUtils.setGlobalHandler((error, isFatal) => {
    if (isFatal) {
      try {
        const record: CrashRecord = { error: format(error), at: new Date().toISOString(), version };
        storage.setItem(KEY, JSON.stringify(record));
      } catch {
        // Never let crash recording hide the original error.
      }
    }
    previous(error, isFatal);
  });
}

export function lastCrash(): CrashRecord | null {
  try {
    const raw = storage.getItem(KEY);
    return typeof raw === 'string' ? (JSON.parse(raw) as CrashRecord) : null;
  } catch {
    return null;
  }
}

export function clearLastCrash() {
  storage.removeItem(KEY);
}
