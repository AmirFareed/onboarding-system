import {
  Activity,
  BarChart3,
  ClipboardCheck,
  FileText,
  FolderOpen,
  History,
  LayoutDashboard,
  MessageSquare,
  RefreshCw,
  ScrollText,
  Settings,
  UserCheck,
} from 'lucide-react';

/**
 * Sidebar navigation model, organised into employee-facing sections.
 *
 * Each section groups top-level links only. Feedback collection and Continuous
 * Learning are internal administrative functions and are deliberately not
 * sidebar entries: they hang off the Settings item as admin-only child links
 * and are surfaced on the Settings page. Application History, Performance and
 * System Logs are IT-only operational views and are top-level System entries
 * restricted to the IT role. Internal document-processing stages (technical validation,
 * extraction, confidence, normalisation, business rules, ...) are
 * intentionally absent: they run automatically as part of application
 * verification and will surface later inside an application's status view,
 * not as sidebar navigation.
 *
 * Role visibility: an item with a `roles` array is shown to users whose
 * canonical role is listed, with Employee allowed through normal role gates.
 * An item with `strictRoles` requires an exact canonical role. Items without
 * either list are shown to every authenticated user. This is a UI/UX gate only:
 * routes stay registered and the backend 403 remains the security gate.
 */
export const NAVIGATION = [
  {
    id: 'main',
    label: 'Main',
    items: [
      { id: 'dashboard', label: 'Dashboard', path: '/', icon: LayoutDashboard },
      { id: 'applications', label: 'Applications', path: '/applications', icon: FolderOpen },
    ],
  },
  {
    id: 'documents',
    label: 'Documents',
    items: [
      { id: 'processing', label: 'Processing', path: '/processing', icon: Activity },
    ],
  },
  {
    id: 'verification',
    label: 'Verification',
    items: [
      { id: 'validation', label: 'Validation', path: '/validation', icon: ClipboardCheck, roles: ['OPERATOR'] },
      { id: 'reports', label: 'Validation Report', path: '/reports', icon: FileText, roles: ['REVIEWER'] },
      { id: 'human-review', label: 'Human Review', path: '/human-review', icon: UserCheck, roles: ['REVIEWER'] },
    ],
  },
  {
    id: 'system',
    label: 'System',
    items: [
      {
        id: 'application-history',
        label: 'Application History',
        path: '/application-history',
        icon: History,
        strictRoles: ['IT'],
      },
      {
        id: 'performance',
        label: 'Performance',
        path: '/performance',
        icon: BarChart3,
        strictRoles: ['IT'],
      },
      {
        id: 'system-logs',
        label: 'System Logs',
        path: '/system-logs',
        icon: ScrollText,
        strictRoles: ['IT'],
      },
      {
        id: 'settings',
        label: 'Settings',
        path: '/settings',
        icon: Settings,
        children: [
          { id: 'feedback', label: 'Feedback', path: '/feedback', icon: MessageSquare, adminOnly: true, roles: ['IT'] },
          { id: 'continuous-learning', label: 'Continuous Learning', path: '/continuous-learning', icon: RefreshCw, adminOnly: true, roles: ['IT'] },
        ],
      },
    ],
  },
];

/** Flat list of every sidebar navigation leaf, in display order. */
export const NAV_ITEMS = NAVIGATION.flatMap(({ items }) => items);

/**
 * Admin-only navigation leaves nested under a parent sidebar entry.
 *
 * These are not shown as top-level sidebar items; they are reached from the
 * Settings page (under Administration) and stay marked as restricted.
 */
export const ADMIN_NAV_ITEMS = NAV_ITEMS.flatMap((item) => item.children ?? []);

/**
 * Internal routes that stay reachable (for future application-level workflow
 * screens and testing) but are not exposed in the sidebar.
 */
export const INTERNAL_ROUTES = [
  { id: 'completeness', label: 'Document Completeness', path: '/completeness' },
  { id: 'technical-validation', label: 'Technical Validation', path: '/technical-validation' },
  { id: 'extraction', label: 'Field Extraction', path: '/extraction' },
  { id: 'confidence', label: 'Confidence Review', path: '/confidence' },
  { id: 'normalization', label: 'Normalization', path: '/normalization' },
  { id: 'business-rules', label: 'Business Rules', path: '/business-rules' },
];

/**
 * Look up a navigation entry by its route path.
 *
 * Nested module routes (e.g. "/applications/12/upload") are matched against the
 * nav path as a path boundary prefix so the navbar always reflects the parent
 * module. Exact matches win; the Dashboard entry is the fallback.
 *
 * @param {string} path The current location pathname.
 * @returns {object} The matching nav entry, defaulting to Dashboard.
 */
export function findNavItem(path) {
  const all = [...NAV_ITEMS, ...ADMIN_NAV_ITEMS];
  const exact = all.find((item) => item.path === path);
  if (exact) {
    if (exact.adminOnly || exact.itOnly) {
      return NAV_ITEMS.find((item) => item.children?.some((child) => child.id === exact.id)) ?? exact;
    }
    return exact;
  }
  const prefixed = all.filter(
    (item) => item.path !== '/' && path.startsWith(`${item.path}/`)
  );
  const match = prefixed.sort((a, b) => b.path.length - a.path.length)[0];
  if (match) {
    return NAV_ITEMS.find((item) => item.children?.some((child) => child.id === match.id)) ?? match;
  }
  return NAV_ITEMS[0];
}
