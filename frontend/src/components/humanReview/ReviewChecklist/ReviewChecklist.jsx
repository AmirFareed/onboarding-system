import { useState } from 'react';

import { CheckCircle2, Eye } from 'lucide-react';

import DocumentViewer from '../../common/DocumentViewer/DocumentViewer';
import styles from './ReviewChecklist.module.css';

/**
 * Manual verification checklist.
 *
 * Renders checklist items grouped by category. Each item has a semantic status
 * (ACTIONABLE or NOT_VERIFIABLE) derived from document availability. Items
 * tied to missing documents are NOT_VERIFIABLE and don't block approval.
 *
 * AMC originality is rendered as a special View→Confirm workflow rather than
 * a normal checkbox. The reviewer must open the AMC before confirming.
 *
 * @param {object} props
 * @param {object[]} props.requirements Derived checklist requirements with semantic status.
 * @param {object} props.checked Map of item name to boolean (checked state).
 * @param {Function} props.onToggle Toggle handler (item name).
 * @param {boolean} props.readOnly Disable toggling.
 * @param {boolean} props.amcViewed Whether the AMC has been opened.
 * @param {Function} props.onAmcView Called when the reviewer clicks View AMC.
 * @param {string|null} props.amcViewUrl Inline view URL for the AMC document.
 * @param {string|null} props.amcDownloadUrl Download URL for the AMC document.
 */
function ReviewChecklist({
  requirements,
  checked,
  onToggle,
  readOnly = false,
  amcViewed = false,
  onAmcView,
  amcViewUrl,
  amcDownloadUrl,
}) {
  const [viewerOpen, setViewerOpen] = useState(false);

  if (!requirements || requirements.length === 0) {
    return (
      <p className={styles.empty}>No checklist items are defined for this review.</p>
    );
  }

  const groups = groupRequirements(requirements);

  const actionableItems = requirements.filter((item) => item.semanticStatus === 'ACTIONABLE');
  const confirmedActionable = actionableItems.filter((item) => checked[item.item_name]).length;

  const handleAmcViewClick = () => {
    if (onAmcView) onAmcView();
    setViewerOpen(true);
  };

  return (
    <div className={styles.container}>
      <div className={styles.heading}>
        <span className={styles.count}>
          <CheckCircle2 className={styles.countIcon} aria-hidden="true" />
          {confirmedActionable} of {actionableItems.length} verified
        </span>
        <span className={styles.hint}>
          Only actionable items are required to approve. NOT_VERIFIABLE items are skipped.
        </span>
      </div>

      {groups.map((group) => (
        <div key={group.key} className={styles.group}>
          <div className={styles.groupHeader}>
            <h4 className={styles.groupTitle}>{group.label}</h4>
            <span className={styles.groupCount}>
              {group.confirmedActionable} / {group.actionableCount} actionable verified
              {group.nvCount > 0 && <> · {group.nvCount} not verifiable</>}
            </span>
          </div>

          <ul className={styles.list}>
            {group.items.map((item) => {
              if (item.isAmcOriginality) {
                return (
                  <li key={item.itemName} className={styles.amcCard}>
                    <AmcOriginalityRow
                      item={item}
                      checked={checked[item.item_name]}
                      readOnly={readOnly}
                      amcViewed={amcViewed}
                      onAmcViewClick={handleAmcViewClick}
                      onToggle={onToggle}
                    />
                  </li>
                );
              }

              const isNotVerifiable = item.semanticStatus === 'NOT_VERIFIABLE';
              return (
                <li
                  key={item.itemName}
                  className={`${styles.row} ${isNotVerifiable ? styles.notVerifiable : ''}`}
                >
                  <label className={styles.label}>
                    <input
                      type="checkbox"
                      className={styles.checkbox}
                      checked={Boolean(checked[item.item_name])}
                      disabled={readOnly || isNotVerifiable}
                      onChange={() => onToggle(item.item_name)}
                    />
                    <span className={styles.itemName}>{item.label}</span>
                  </label>

                  {isNotVerifiable && (
                    <span className={styles.nvBadge}>Not Verifiable</span>
                  )}

                  {!isNotVerifiable && item.is_checked && item.reviewer && item.checked_at && (
                    <span className={styles.reviewedBy}>
                      by {item.reviewer}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}

      <DocumentViewer
        open={viewerOpen}
        viewUrl={amcViewUrl}
        downloadUrl={amcDownloadUrl}
        title="Account Maintenance Certificate"
        onClose={() => setViewerOpen(false)}
      />
    </div>
  );
}

/**
 * Special card for AMC originality with View→Confirm workflow.
 */
function AmcOriginalityRow({ item, checked, readOnly, amcViewed, onAmcViewClick, onToggle }) {
  const isNotVerifiable = item.semanticStatus === 'NOT_VERIFIABLE';
  const isConfirmed = Boolean(checked);

  if (isNotVerifiable) {
    return (
      <div className={styles.amcContent}>
        <span className={styles.amcTitle}>{item.label}</span>
        <span className={styles.amcNotVerifiable}>— Not Verifiable</span>
        <p className={styles.amcNote}>Account Maintenance Certificate is missing.</p>
      </div>
    );
  }

  return (
    <div className={styles.amcContent}>
      <div className={styles.amcHeader}>
        <span className={styles.amcTitle}>{item.label}</span>
        {isConfirmed ? (
          <span className={styles.amcConfirmed}>✓ Originality Confirmed</span>
        ) : (
          <span className={styles.amcWarning}>⚠ Manual Verification Required</span>
        )}
      </div>

      <p className={styles.amcNote}>
        The system cannot automatically verify the originality of this document.
        Please review the Account Maintenance Certificate before confirming.
      </p>

      <div className={styles.amcActions}>
        <button
          type="button"
          className={styles.amcViewBtn}
          onClick={onAmcViewClick}
          disabled={readOnly}
        >
          <Eye aria-hidden="true" />
          View AMC
        </button>

        <button
          type="button"
          className={`${styles.amcConfirmBtn} ${isConfirmed ? styles.amcConfirmBtnConfirmed : ''}`}
          disabled={readOnly || (!amcViewed && !isConfirmed)}
          onClick={() => onToggle(item.item_name)}
        >
          {isConfirmed ? '✓ Originality Confirmed' : '✓ Confirm Originality'}
        </button>
      </div>
    </div>
  );
}

/**
 * Group checklist requirements by category.
 */
function groupRequirements(requirements) {
  const groupMap = new Map();

  for (const item of requirements) {
    const groupKey = item.group;
    if (!groupMap.has(groupKey)) {
      groupMap.set(groupKey, {
        key: groupKey,
        label: item.groupLabel,
        items: [],
        actionableCount: 0,
        confirmedActionable: 0,
        nvCount: 0,
      });
    }
    const group = groupMap.get(groupKey);
    group.items.push(item);
    if (item.semanticStatus === 'ACTIONABLE') {
      group.actionableCount += 1;
    }
    if (item.semanticStatus === 'ACTIONABLE' && item.is_checked) {
      group.confirmedActionable += 1;
    }
    if (item.semanticStatus === 'NOT_VERIFIABLE') {
      group.nvCount += 1;
    }
  }

  return [...groupMap.values()];
}

export default ReviewChecklist;
