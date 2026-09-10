import { useEffect, useRef, useState } from 'react';

import { Check } from 'lucide-react';

import Toggle from '../../common/Toggle/Toggle';
import styles from './PreferenceRow.module.css';

const SAVED_MS = 1500;

/**
 * One workspace preference row.
 *
 * Renders an icon chip, a title and concise description, an accessible switch
 * and a brief "Saved" confirmation that appears after a change.
 *
 * @param {object} props
 * @param {string} props.id Unique control id.
 * @param {string} props.title Preference label.
 * @param {string} props.description Concise explanation of the behaviour.
 * @param {boolean} props.value Current preference value.
 * @param {Function} props.onChange Callback with the next value.
 * @param {object} props.icon Lucide icon component for the row chip.
 */
function PreferenceRow({ id, title, description, value, onChange, icon: Icon }) {
  const [saved, setSaved] = useState(false);
  const savedTimerRef = useRef(null);

  useEffect(() => () => window.clearTimeout(savedTimerRef.current), []);

  const handleChange = (next) => {
    onChange(next);
    setSaved(true);
    window.clearTimeout(savedTimerRef.current);
    savedTimerRef.current = window.setTimeout(() => setSaved(false), SAVED_MS);
  };

  return (
    <div className={styles.row}>
      <span className={styles.icon} aria-hidden="true">
        {Icon && <Icon />}
      </span>
      <div className={styles.meta}>
        <span className={styles.titleRow}>
          <span className={styles.title}>{title}</span>
          <span className={`${styles.saved} ${saved ? styles.visible : ''}`} role="status" aria-live="polite">
            <Check aria-hidden="true" />
            Saved
          </span>
        </span>
        <span className={styles.description}>{description}</span>
      </div>
      <div className={styles.control}>
        <Toggle
          id={id}
          checked={Boolean(value)}
          aria-label={title}
          onChange={handleChange}
        />
      </div>
    </div>
  );
}

export default PreferenceRow;
