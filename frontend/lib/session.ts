/**
 * Client-side session identity.
 *
 * A "session" is a lightweight, anonymous browsing session used to power
 * session-based recommendations (see `movieApi.getSessionRecommendations`
 * and `movieApi.trackSessionInteraction` in `../api`). The id is generated
 * once per browser and persisted in `localStorage` so it survives page
 * reloads within the same tab/browser, but is not tied to a logged-in user.
 */

const SESSION_STORAGE_KEY = 'cinevault_session_id';

/**
 * Return the current session id, creating and persisting a new one on first
 * call. Returns `null` when running outside the browser (SSR/build time),
 * since there is no `localStorage` to read from or write to there.
 */
export function getSessionId(): string | null {
    if (typeof window === 'undefined' || !window.localStorage) {
        return null;
    }

    try {
        const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
        if (existing) {
            return existing;
        }

        const sessionId = generateSessionId();
        window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
        return sessionId;
    } catch {
        // localStorage can throw (e.g. private browsing quota errors) —
        // degrade gracefully rather than breaking the caller.
        return null;
    }
}

/** Clear the persisted session id, forcing a new one on next access. */
export function resetSessionId(): void {
    if (typeof window === 'undefined' || !window.localStorage) {
        return;
    }
    try {
        window.localStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
        // ignore
    }
}

function generateSessionId(): string {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    // Fallback for environments without crypto.randomUUID
    return `sess_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}
