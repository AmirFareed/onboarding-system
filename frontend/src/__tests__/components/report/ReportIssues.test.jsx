import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ReportIssues from '../../../components/report/ReportIssues/ReportIssues';

// docs/TEAMMATE_BUG_TRIAGE.md's corrected Medium #9: `groupIssues(issues ?? [])`
// guarded the grouping call, but the empty-state check read the raw `issues`
// prop directly, so an undefined/null `issues` still crashed on `.length`.
describe('ReportIssues', () => {
  it('does not throw when issues is undefined', () => {
    expect(() =>
      render(<ReportIssues issues={undefined} recommendations={[]} />)
    ).not.toThrow();
    expect(
      screen.getByText(/no issues requiring attention/i)
    ).toBeInTheDocument();
  });

  it('does not throw when issues is null', () => {
    expect(() =>
      render(<ReportIssues issues={null} recommendations={[]} />)
    ).not.toThrow();
    expect(
      screen.getByText(/no issues requiring attention/i)
    ).toBeInTheDocument();
  });

  it('still groups and renders real issues normally', () => {
    render(
      <ReportIssues
        issues={[
          { title: 'Missing signature', status: 'FAIL', severity: 'ERROR' },
          { title: 'Low confidence', status: 'WARNING', severity: 'WARNING' },
        ]}
        recommendations={[]}
      />
    );

    expect(screen.getByText('Critical issues')).toBeInTheDocument();
    expect(screen.getByText('Missing signature')).toBeInTheDocument();
    expect(screen.getByText('Warnings')).toBeInTheDocument();
    expect(screen.getByText('Low confidence')).toBeInTheDocument();
  });
});
