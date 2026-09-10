import { Inbox } from 'lucide-react';
import styles from './EmptyState.module.css';

/**
 * Placeholder shown when a list or section has no rows.
 *
 * @param {object} props
 * @param {string} [props.title] Heading text.
 * @param {string} [props.message] Supporting explanation.
 * @param {import('react').ReactNode} [props.action] Optional action element
 *   (e.g. a link or button) rendered below the message.
 */
function EmptyState({ title = 'Nothing here yet', message, action }) {
  return (
    <div className={styles.empty}>
      <div className={styles.iconWrap} aria-hidden="true">
        <Inbox />
      </div>
      <h3 className={styles.title}>{title}</h3>
      {message && <p className={styles.message}>{message}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}

export default EmptyState;
