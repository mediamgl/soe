// Module-level registry of "flush-before-exit" callbacks.
//
// Any component that holds debounced writes (scenario autosave, etc.) can
// register a flusher on mount and unregister on unmount. SaveExitModal
// (and, in future, any other pre-navigation handler) awaits flushAll()
// before tearing down the session.
//
// A flusher MUST return a Promise that resolves when the write has landed
// (or has failed silently — never throw: exit must never be blocked).
//
// flushAll() races the flushers against a hard deadline so a wedged
// network doesn't prevent the user from leaving.

const flushers = new Set();

export function registerFlusher(fn) {
  if (typeof fn !== 'function') return () => {};
  flushers.add(fn);
  return () => { flushers.delete(fn); };
}

export async function flushAll({ timeoutMs = 3000 } = {}) {
  if (flushers.size === 0) return;
  const tasks = Array.from(flushers).map((fn) => {
    try {
      return Promise.resolve(fn());
    } catch {
      return Promise.resolve();
    }
  });
  const all = Promise.allSettled(tasks);
  const timeout = new Promise((resolve) => setTimeout(resolve, timeoutMs));
  await Promise.race([all, timeout]);
}
