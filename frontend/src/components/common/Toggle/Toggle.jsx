import styles from './Toggle.module.css';

/**
 * Accessible switch control.
 *
 * Renders a real checkbox (role switch) with a themed track and thumb. The
 * visual state, hover, focus-visible ring and disabled style all come from the
 * design tokens, so the switch adapts to every theme automatically.
 *
 * @param {object} props
 * @param {boolean} props.checked Whether the switch is on.
 * @param {Function} props.onChange Callback with the next checked value.
 * @param {string} [props.id] Optional id for label association.
 * @param {string} [props['aria-label']] Accessible name when not paired with a label.
 * @param {boolean} [props.disabled] Disable the switch.
 */
function Toggle({ checked, onChange, id, 'aria-label': ariaLabel, disabled = false }) {
  return (
    <span
      className={`${styles.switch} ${checked ? styles.on : styles.off} ${disabled ? styles.disabled : ''}`}
    >
      <input
        id={id}
        type="checkbox"
        role="switch"
        className={styles.input}
        checked={checked}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className={styles.thumb} />
    </span>
  );
}

export default Toggle;
