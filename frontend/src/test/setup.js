import '@testing-library/jest-dom';

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
