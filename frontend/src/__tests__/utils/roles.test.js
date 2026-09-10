import { describe, expect, it } from 'vitest';

import {
  effectiveRole,
  isEmployee,
  isIt,
  isOperator,
  isReviewer,
  visibleNavigationFor,
} from '../../utils/roles';

const ALL_NAV_IDS = [
  'dashboard',
  'applications',
  'processing',
  'validation',
  'reports',
  'human-review',
  'application-history',
  'performance',
  'system-logs',
  'settings',
];

function visibleIds(user) {
  return visibleNavigationFor(user)
    .flatMap((section) => section.items)
    .map((item) => item.id);
}

describe('effectiveRole', () => {
  it('defaults a missing role to OPERATOR', () => {
    expect(effectiveRole(null)).toBe('OPERATOR');
    expect(effectiveRole('')).toBe('OPERATOR');
  });

  it('passes canonical roles through unchanged', () => {
    expect(effectiveRole('EMPLOYEE')).toBe('EMPLOYEE');
    expect(effectiveRole('OPERATOR')).toBe('OPERATOR');
    expect(effectiveRole('REVIEWER')).toBe('REVIEWER');
    expect(effectiveRole('IT')).toBe('IT');
  });

  it('maps the legacy "Verification Officer" role to EMPLOYEE', () => {
    expect(effectiveRole('Verification Officer')).toBe('EMPLOYEE');
  });

  it('passes unknown strings through unchanged', () => {
    expect(effectiveRole('SUPERVISOR')).toBe('SUPERVISOR');
  });
});

describe('role predicates', () => {
  it('treats the "Verification Officer" account as the all-access Employee', () => {
    expect(isEmployee({ role: 'Verification Officer' })).toBe(true);
    expect(isEmployee({ role: 'EMPLOYEE' })).toBe(true);
    expect(isEmployee({ role: 'OPERATOR' })).toBe(false);
    expect(isEmployee({ role: 'REVIEWER' })).toBe(false);
    expect(isEmployee({ role: 'IT' })).toBe(false);
    expect(isEmployee({ role: 'SUPERVISOR' })).toBe(false);
  });

  it('resolves predicates against the canonical role', () => {
    expect(isOperator({ role: 'Verification Officer' })).toBe(false);
    expect(isReviewer({ role: 'Verification Officer' })).toBe(false);
    expect(isOperator({ role: 'OPERATOR' })).toBe(true);
    expect(isReviewer({ role: 'REVIEWER' })).toBe(true);
    expect(isIt({ role: 'IT' })).toBe(true);
  });
});

describe('visibleNavigationFor', () => {
  it('hides strict IT reporting pages from the all-access Employee account', () => {
    expect(visibleIds({ role: 'Verification Officer' }).sort()).toEqual(
      ALL_NAV_IDS.filter(
        (id) => !['application-history', 'performance', 'system-logs'].includes(id)
      ).sort()
    );
  });

  it('restricts an unknown custom role to the ungated items', () => {
    expect(visibleIds({ role: 'SUPERVISOR' }).sort()).toEqual(
      ['dashboard', 'applications', 'processing', 'settings'].sort()
    );
  });

  it('restricts an OPERATOR to applications, processing and validation', () => {
    expect(visibleIds({ role: 'OPERATOR' }).sort()).toEqual(
      ['dashboard', 'applications', 'processing', 'validation', 'settings'].sort()
    );
  });

  it('restricts a REVIEWER to applications, processing, reports and human review', () => {
    expect(visibleIds({ role: 'REVIEWER' }).sort()).toEqual(
      ['dashboard', 'applications', 'processing', 'reports', 'human-review', 'settings'].sort()
    );
  });

  it('restricts IT to applications, processing, history, performance and system logs', () => {
    expect(visibleIds({ role: 'IT' }).sort()).toEqual(
      [
        'dashboard',
        'applications',
        'processing',
        'application-history',
        'performance',
        'system-logs',
        'settings',
      ].sort()
    );
  });

  it('drops child admin links (feedback, continuous learning) for a REVIEWER', () => {
    const sections = visibleNavigationFor({ role: 'REVIEWER' });
    const settingsChildren = sections
      .flatMap((section) => section.items)
      .find((item) => item.id === 'settings')?.children;
    expect(settingsChildren).toEqual([]);
  });
});
