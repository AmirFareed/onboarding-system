import { useEffect, useRef, useState } from 'react';
import { Check, Cherry, Leaf, Moon, MoonStar, Sun } from 'lucide-react';

import { useTheme } from '../../../hooks/useTheme';
import { THEME_OPTIONS } from '../../../theme/theme';
import styles from './ThemeToggle.module.css';

const OPTIONS = {
  light: { icon: Sun, label: 'Light' },
  dark: { icon: Moon, label: 'Dark' },
  black: { icon: MoonStar, label: 'Black' },
  mint: { icon: Leaf, label: 'Mint' },
  cherry: { icon: Cherry, label: 'Cherry' },
};

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handleClickOutside = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  const ActiveIcon = OPTIONS[theme].icon;

  return (
    <div className={styles.wrap} ref={rootRef}>
      <button
        className={styles.trigger}
        type="button"
        aria-label="Change theme"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <ActiveIcon aria-hidden="true" />
      </button>

      {open && (
        <div className={styles.menu} role="menu" aria-label="Theme options">
          {THEME_OPTIONS.map((option) => {
            const meta = OPTIONS[option];
            const Icon = meta.icon;
            const selected = option === theme;
            return (
              <button
                key={option}
                className={`${styles.item} ${selected ? styles.selected : ''}`}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                onClick={() => {
                  setTheme(option);
                  setOpen(false);
                }}
              >
                <Icon className={styles.itemIcon} aria-hidden="true" />
                <span className={styles.itemLabel}>{meta.label}</span>
                {selected && <Check className={styles.check} aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default ThemeToggle;
