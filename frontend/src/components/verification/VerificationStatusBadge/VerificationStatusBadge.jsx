import StatusChip from '../../common/StatusChip/StatusChip';
import { getVerificationStatus } from '../../../data/statuses';

/**
 * Employee-facing pill for a raw validation status value.
 *
 * Resolves backend enums (PASS, WARNING, PENDING_MANUAL_REVIEW, FAIL,
 * REJECTED) through the shared status catalogue so internal enum names never
 * reach the UI. Also accepts derived per-document statuses (VERIFIED,
 * REVIEW_REQUIRED, FAILED, MISSING, PENDING) via the same lookup.
 *
 * @param {object} props
 * @param {string} props.status Raw or derived verification status value.
 */
function VerificationStatusBadge({ status }) {
  const entry = getVerificationStatus(status);
  return <StatusChip label={entry.label} variant={entry.variant} />;
}

export default VerificationStatusBadge;
