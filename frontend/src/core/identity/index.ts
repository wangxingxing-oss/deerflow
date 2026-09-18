import { uuid } from "../utils/uuid";

/** localStorage key that stores this browser's anonymous identity. */
export const CLIENT_ID_STORAGE_KEY = "deer-flow.client-id";

/** Thread metadata key that records which browser a thread belongs to. */
export const THREAD_OWNER_METADATA_KEY = "owner_id";

let cachedClientId: string | null = null;

/**
 * Anonymous identity of the current browser, generated and persisted on first
 * use. All tabs of the same browser and origin share one identity, so this
 * separates browsers/devices without requiring a login.
 */
export function getClientId(): string {
  if (cachedClientId) {
    return cachedClientId;
  }
  if (typeof window === "undefined") {
    return "server";
  }
  try {
    const stored = window.localStorage.getItem(CLIENT_ID_STORAGE_KEY);
    if (stored) {
      cachedClientId = stored;
    } else {
      cachedClientId = uuid();
      window.localStorage.setItem(CLIENT_ID_STORAGE_KEY, cachedClientId);
    }
  } catch {
    // localStorage can be unavailable (e.g. blocked storage); degrade to an
    // in-memory id so the app keeps working, just without cross-tab stability.
    cachedClientId = uuid();
  }
  return cachedClientId;
}

/** Metadata that stamps a thread as belonging to the current browser. */
export function ownerMetadata(): Record<string, string> {
  return { [THREAD_OWNER_METADATA_KEY]: getClientId() };
}
