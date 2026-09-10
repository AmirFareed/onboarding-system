import { Link2 } from 'lucide-react';

import VerificationStatusBadge from '../VerificationStatusBadge/VerificationStatusBadge';
import styles from './CrossDocumentPanel.module.css';

/**
 * Cross-document consistency panel.
 *
 * Lists only the cross-document rules (IBAN, account number, holder name and
 * similar values matched across documents). Each entry names the checked value
 * and the documents involved; internal rule ids stay hidden.
 *
 * @param {object} props
 * @param {object[]} props.rules Cross-document rule outcomes.
 */
function CrossDocumentPanel({ rules }) {
  return (
    <section className={styles.panel} aria-label="Cross-document verification">
      <div className={styles.header}>
        <div className={styles.iconWrap} aria-hidden="true">
          <Link2 />
        </div>
        <div>
          <h3 className={styles.title}>Cross-document Verification</h3>
          <p className={styles.subtitle}>
            Values checked for consistency across documents.
          </p>
        </div>
      </div>

      {rules.length === 0 ? (
        <p className={styles.empty}>No cross-document consistency checks yet.</p>
      ) : (
        <ul className={styles.list}>
          {rules.map((rule, index) => (
            <li key={`${rule.rule_name}-${index}`} className={styles.item}>
              <div className={styles.itemHeader}>
                <span className={styles.itemName}>{rule.rule_name}</span>
                <VerificationStatusBadge status={rule.status} />
              </div>
              {rule.message && <p className={styles.itemMessage}>{rule.message}</p>}
              {rule.related_document_ids.length > 0 && (
                <div className={styles.documents}>
                  {rule.related_document_ids.map((id) => (
                    <span key={id} className={styles.documentTag}>
                      #{id}
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default CrossDocumentPanel;
