import { useEffect, useState } from 'react';

/**
 * Subscribe to a CSS media query and report whether it currently matches.
 *
 * Used by the dashboard layout to switch between desktop, tablet and mobile
 * navigation behaviour without duplicating breakpoint logic in components.
 *
 * @param {string} query A CSS media query string, e.g. "(min-width: 1024px)".
 * @returns {boolean} True when the query currently matches.
 */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const media = window.matchMedia(query);
    const handleChange = () => setMatches(media.matches);
    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, [query]);

  return matches;
}
