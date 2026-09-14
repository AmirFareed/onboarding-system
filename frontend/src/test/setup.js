import '@testing-library/jest-dom';

// Node 22+ ships an experimental global Web Storage API that can shadow
// jsdom's own localStorage under Vitest, leaving window.localStorage
// resolving to undefined instead of a real Storage (reproduced locally on
// Node 26; CI runs Node 24, which ships the same experimental feature, so
// this isn't just a local quirk). Any test touching localStorage needs a
// working implementation regardless of the Node version running the suite,
// so fall back to a minimal in-memory polyfill when the real one isn't
// usable.
if (typeof window.localStorage === 'undefined' || window.localStorage === null) {
  const store = new Map();
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => {
        store.set(key, String(value));
      },
      removeItem: (key) => {
        store.delete(key);
      },
      clear: () => {
        store.clear();
      },
      key: (index) => Array.from(store.keys())[index] ?? null,
      get length() {
        return store.size;
      },
    },
  });
}

// jsdom does not implement matchMedia; DashboardLayout (useMediaQuery) and
// the reduced-motion hook both call it unconditionally on mount, so any test
// that renders past the protected layout needs this polyfill.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
}
