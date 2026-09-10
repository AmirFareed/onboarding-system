import { useId } from 'react';

/**
 * FinTech brand mark, rendered as an inline SVG so its colours come from the
 * active theme's design tokens (--color-logo-*) instead of a static file.
 * The shape is identical to the original logo; only the colours change with
 * the theme.
 *
 * @param {object} props
 * @param {string} [props.className] Size/positioning class from the caller.
 * @param {string} [props.alt] Accessible name (defaults to "FinTech logo").
 */
function Logo({ className, alt = 'FinTech logo' }) {
  const gradientId = useId().replace(/[^a-zA-Z0-9_-]/g, '');

  return (
    <svg
      className={className}
      width="40"
      height="40"
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={alt}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="40" y2="40">
          <stop stopColor="var(--color-logo-from)" />
          <stop offset="1" stopColor="var(--color-logo-to)" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill={`url(#${gradientId})`} />
      <path d="M12 13h16v14a2 2 0 0 1-2 2H14a2 2 0 0 1-2-2V13z" fill="#FFFFFF" />
      <path
        d="M15 19h10M15 24h7"
        stroke="var(--color-logo-line)"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default Logo;
