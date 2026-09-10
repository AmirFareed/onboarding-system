import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Check,
  CircleX,
  Copy,
  FileText,
  Filter,
  History,
  Info,
  KeyRound,
  LogOut,
  MessageSquare,
  PlayCircle,
  RefreshCw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
} from 'lucide-react';

import ConfirmDialog from '../../components/common/ConfirmDialog/ConfirmDialog';
import Spinner from '../../components/common/Spinner/Spinner';
import StatusChip from '../../components/common/StatusChip/StatusChip';
import { useToast } from '../../components/common/Toast/ToastContext';
import PreferenceRow from '../../components/settings/PreferenceRow/PreferenceRow';
import { ADMIN_NAV_ITEMS } from '../../data/navigation';
import { useAuth } from '../../hooks/useAuth';
import { humanizeEnum } from '../../utils/format';
import { isEmployee, isIt } from '../../utils/roles';
import { getPreferences, setPreference } from '../../utils/preferences';
import styles from './SettingsPage.module.css';

/**
 * Humanize a backend role value into an employee-facing label.
 */
function roleLabel(role) {
  switch (String(role ?? '').toLowerCase()) {
    case 'admin':
      return 'Administrator';
    case 'reviewer':
      return 'Reviewer';
    case 'operator':
      return 'Operator';
    case 'employee':
      return 'Employee';
    default:
      return role ? humanizeEnum(role) : '—';
  }
}

function initialsOf(name) {
  return String(name ?? '')
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

const PREFERENCE_ITEMS = [
  {
    key: 'rememberApplicationFilter',
    title: 'Remember application filter',
    description: 'Keep the status filter you last used on the Applications list.',
    icon: Filter,
  },
  {
    key: 'rememberLastOpenedApplication',
    title: 'Remember last opened application',
    description: 'Show a resume shortcut to the application you last opened.',
    icon: History,
  },
  {
    key: 'confirmBeforeRejectApplication',
    title: 'Confirm before rejecting an application',
    description: 'Require explicit confirmation before an application is rejected.',
    icon: CircleX,
  },
  {
    key: 'autoStartProcessingAfterUpload',
    title: 'Start processing after upload',
    description: 'Automatically begin document processing once an upload succeeds.',
    icon: PlayCircle,
  },
  {
    key: 'autoRefreshProcessingStatus',
    title: 'Automatically refresh processing status',
    description: 'Poll processing progress while you wait. Disable to refresh manually.',
    icon: RefreshCw,
  },
  {
    key: 'openReportOnProcessingComplete',
    title: 'Open validation report when processing completes',
    description: 'Jump to the validation report as soon as processing finishes.',
    icon: FileText,
  },
];

/**
 * Copy a value to the clipboard with a graceful fallback.
 *
 * @returns {Promise<boolean>} Whether the copy succeeded.
 */
async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    try {
      const textarea = document.createElement('textarea');
      textarea.value = value;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand('copy');
      document.body.removeChild(textarea);
      return copied;
    } catch {
      return false;
    }
  }
}

/**
 * Settings page.
 *
 * Shows the signed-in user's profile and session information from the
 * authenticated /auth/me contract, a functional workspace-preferences panel
 * persisted on the device, a confirmed sign-out, an honest password/security
 * notice and the restricted Administration tools. No backend endpoint is
 * fabricated: profile editing and password changes are intentionally absent.
 */
function SettingsPage() {
  const { user, authenticated, loading, logout } = useAuth();
  const toast = useToast();
  const [preferences, setPreferences] = useState(getPreferences);
  const [signingOut, setSigningOut] = useState(false);
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const [copiedField, setCopiedField] = useState(null);

  const displayName = user?.name ?? '—';
  const initials = initialsOf(user?.name) || 'U';

  const handlePreferenceChange = (key, value) => {
    setPreference(key, value);
    setPreferences(getPreferences());
  };

  const handleCopy = async (field, label, value) => {
    if (!value) {
      return;
    }
    const ok = await copyText(value);
    if (ok) {
      setCopiedField(field);
      toast.success(`${label} copied to clipboard.`);
      window.setTimeout(() => setCopiedField((current) => (current === field ? null : current)), 1600);
    } else {
      toast.error('Unable to copy. Please copy the value manually.');
    }
  };

  const handleSignOut = async () => {
    setConfirmSignOut(false);
    setSigningOut(true);
    try {
      await logout();
    } catch {
      toast.error('Sign out failed. Your local session has been cleared.');
    } finally {
      setSigningOut(false);
    }
  };

  const showAdministration = isEmployee(user) || isIt(user);

  const administrationItems = ADMIN_NAV_ITEMS.filter((item) => !item.itOnly).map((item) => {
    const iconByType = {
      feedback: MessageSquare,
      'continuous-learning': RefreshCw,
    };
    const Icon = iconByType[item.id] ?? MessageSquare;
    return { ...item, Icon };
  });

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerTitle}>
          <span className={styles.headerIcon} aria-hidden="true">
            <Settings2 />
          </span>
          <div>
            <h2 className={styles.title}>Settings</h2>
            <p className={styles.subtitle}>
              Your profile, workspace preferences and session management.
            </p>
          </div>
        </div>
      </header>

      {loading ? (
        <div className={styles.loadingWrap} aria-busy="true">
          <Spinner size="medium" />
          <p className={styles.loadingText}>Loading your profile…</p>
        </div>
      ) : (
        <>
          <section className={styles.card} aria-label="Profile information">
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon} aria-hidden="true">
                <UserRound />
              </span>
              <div className={styles.cardTitleWrap}>
                <h3 className={styles.cardTitle}>Profile</h3>
                <p className={styles.cardDescription}>
                  Your employee profile as recorded for this workspace.
                </p>
              </div>
              <StatusChip label="Session active" variant="success" />
            </div>

            <div className={styles.profileHeader}>
              <span className={styles.avatar} aria-hidden="true">
                {initials}
              </span>
              <div className={styles.profileMeta}>
                <span className={styles.profileName}>{displayName}</span>
                <span className={styles.profileRole}>{roleLabel(user?.role)}</span>
              </div>
            </div>

            <dl className={styles.details}>
              <div className={styles.detailRow}>
                <dt>Name</dt>
                <dd>{user?.name ?? '—'}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Email</dt>
                <dd className={styles.detailValueRow}>
                  <span className={styles.detailValue}>{user?.email ?? '—'}</span>
                  {user?.email && (
                    <button
                      type="button"
                      className={styles.copyBtn}
                      aria-label="Copy email address"
                      onClick={() => handleCopy('email', 'Email', user.email)}
                    >
                      {copiedField === 'email' ? (
                        <Check aria-hidden="true" />
                      ) : (
                        <Copy aria-hidden="true" />
                      )}
                    </button>
                  )}
                </dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Employee ID</dt>
                <dd className={styles.detailValueRow}>
                  <span className={styles.detailValue}>{user?.employee_id ?? '—'}</span>
                  {user?.employee_id && (
                    <button
                      type="button"
                      className={styles.copyBtn}
                      aria-label="Copy employee ID"
                      onClick={() => handleCopy('employeeId', 'Employee ID', user.employee_id)}
                    >
                      {copiedField === 'employeeId' ? (
                        <Check aria-hidden="true" />
                      ) : (
                        <Copy aria-hidden="true" />
                      )}
                    </button>
                  )}
                </dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Role</dt>
                <dd>{roleLabel(user?.role)}</dd>
              </div>
            </dl>
          </section>

          <section className={styles.card} aria-label="Workspace preferences">
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon} aria-hidden="true">
                <SlidersHorizontal />
              </span>
              <div className={styles.cardTitleWrap}>
                <h3 className={styles.cardTitle}>Workspace Preferences</h3>
                <p className={styles.cardDescription}>
                  Tailor how this workspace behaves while you work.
                </p>
              </div>
            </div>

            <div className={styles.preferenceList}>
              {PREFERENCE_ITEMS.map((item) => (
                <PreferenceRow
                  key={item.key}
                  id={`preference-${item.key}`}
                  title={item.title}
                  description={item.description}
                  icon={item.icon}
                  value={preferences[item.key]}
                  onChange={(next) => handlePreferenceChange(item.key, next)}
                />
              ))}
            </div>

            <p className={styles.storageNote}>
              <Info aria-hidden="true" />
              Changes are stored on this device.
            </p>
          </section>

          <section className={styles.card} aria-label="Account and session">
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon} aria-hidden="true">
                <Settings2 />
              </span>
              <div className={styles.cardTitleWrap}>
                <h3 className={styles.cardTitle}>Account &amp; Session</h3>
                <p className={styles.cardDescription}>
                  Manage the current signed-in session.
                </p>
              </div>
            </div>

            <div className={styles.accountBody}>
              <div className={styles.accountInfo}>
                <div className={styles.accountRow}>
                  <span className={styles.accountLabel}>Signed in as</span>
                  <span className={styles.accountValue}>
                    {authenticated ? displayName : 'Not signed in'}
                  </span>
                </div>
                <div className={styles.accountRow}>
                  <span className={styles.accountLabel}>Role</span>
                  <span className={styles.accountValue}>{roleLabel(user?.role)}</span>
                </div>
                <div className={styles.accountRow}>
                  <span className={styles.accountLabel}>Session</span>
                  <StatusChip label={authenticated ? 'Session active' : 'Signed out'} variant={authenticated ? 'success' : 'neutral'} />
                </div>
              </div>

              <div className={styles.signOutWrap}>
                <p className={styles.bodyHint}>
                  Signing out ends your session on this device. You can sign back in with your
                  employee credentials at any time.
                </p>
                <button
                  type="button"
                  className={styles.signOutBtn}
                  onClick={() => setConfirmSignOut(true)}
                  disabled={signingOut}
                >
                  {signingOut ? <Spinner size="small" /> : <LogOut aria-hidden="true" />}
                  {signingOut ? 'Signing out…' : 'Sign out'}
                </button>
              </div>
            </div>
          </section>

          <section className={styles.card} aria-label="Password and security">
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon} aria-hidden="true">
                <KeyRound />
              </span>
              <div className={styles.cardTitleWrap}>
                <h3 className={styles.cardTitle}>Password &amp; Security</h3>
                <p className={styles.cardDescription}>
                  How access to your account is managed.
                </p>
              </div>
            </div>
            <div className={styles.securityBody}>
              <span className={styles.securityIcon} aria-hidden="true">
                <ShieldCheck />
              </span>
              <div className={styles.securityText}>
                <p className={styles.securityTitle}>
                  Password and account security are managed by your administrator.
                </p>
                <p className={styles.securityDescription}>
                  Password changes are not available in this application. For password resets,
                  multi-factor authentication or any account security request, contact your
                  administrator.
                </p>
              </div>
            </div>
          </section>

          {showAdministration && (
            <section className={styles.card} aria-label="Administration settings">
              <div className={styles.cardHeader}>
                <span className={styles.cardIcon} aria-hidden="true">
                  <ShieldCheck />
                </span>
                <div className={styles.cardTitleWrap}>
                  <h3 className={styles.cardTitle}>Administration</h3>
                  <p className={styles.cardDescription}>
                    Internal system and AI dataset management. Restricted by role.
                  </p>
                </div>
                <span className={styles.restricted}>Restricted</span>
              </div>

              <ul className={styles.adminList}>
                {administrationItems.map(({ id, label, path, Icon }) => (
                  <li key={id}>
                    <Link to={path} className={styles.adminLink}>
                      <span className={styles.adminIcon} aria-hidden="true">
                        <Icon />
                      </span>
                      <span className={styles.adminMeta}>
                        <span className={styles.adminLabel}>{label}</span>
                        <span className={styles.adminHint}>
                          {id === 'feedback'
                            ? 'Review correction history and export analytics.'
                            : 'Manage dataset versions, generation and exports.'}
                        </span>
                      </span>
                      <ArrowRight className={styles.adminArrow} aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmSignOut}
        title="Sign out of this workspace?"
        message={`You are signed in as ${displayName}. Signing out ends your session on this device.`}
        confirmLabel="Sign out"
        cancelLabel="Cancel"
        tone="primary"
        loading={signingOut}
        onConfirm={handleSignOut}
        onCancel={() => setConfirmSignOut(false)}
      />
    </div>
  );
}

export default SettingsPage;