import { useEffect, useState } from 'react';

/**
 * Subscribe to the OS-level "reduce motion" preference.
 *
 * Decorations that autoplay (the login video) should not run when this is
 * enabled. The value updates live if the preference changes while the page is
 * open.
 *
 * @returns {boolean} True when the user has requested reduced motion.
 */
export function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  );

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = (event) => setPrefersReducedMotion(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  return prefersReducedMotion;
}
