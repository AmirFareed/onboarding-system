import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ValidationQueueSummary, {
  computeSummaryCounters,
} from '../../components/validationQueue/ValidationQueueSummary/ValidationQueueSummary';

function makeApplication(overrides = {}) {
  return {
    application_id: 1,
    status: 'SUBMITTED',
    needs_attention: false,
    missing_document_count: 0,
    ...overrides,
  };
}

describe('computeSummaryCounters', () => {
  it('returns zeroed counters for an empty queue', () => {
    const counters = computeSummaryCounters([]);
    expect(counters.map((c) => c.count)).toEqual([0, 0, 0, 0, 0]);
  });

  it('counts finalized applications as Completed (priority 1)', () => {
    const counters = computeSummaryCounters([
      makeApplication({ status: 'APPROVED' }),
      makeApplication({ status: 'CORRECTED' }),
    ]);
    expect(counters[4].count).toBe(2);
  });

  it('counts rejected applications (priority 2)', () => {
    const counters = computeSummaryCounters([
      makeApplication({ status: 'REJECTED' }),
      makeApplication({ status: 'APPROVED' }),
    ]);
    expect(counters[3].count).toBe(1);
    expect(counters[4].count).toBe(1);
  });

  it('counts needs-attention applications before missing documents (priority 3)', () => {
    const counters = computeSummaryCounters([
      makeApplication({ needs_attention: true, missing_document_count: 3 }),
    ]);
    expect(counters[2].count).toBe(1);
    expect(counters[1].count).toBe(0);
  });

  it('counts missing-document applications (priority 4)', () => {
    const counters = computeSummaryCounters([
      makeApplication({ missing_document_count: 2 }),
    ]);
    expect(counters[1].count).toBe(1);
  });

  it('counts the rest as pending (priority 5)', () => {
    const counters = computeSummaryCounters([
      makeApplication({ missing_document_count: 0 }),
    ]);
    expect(counters[0].count).toBe(1);
  });

  it('counts each application into exactly one bucket', () => {
    const applications = [
      makeApplication({ status: 'APPROVED' }),
      makeApplication({ status: 'REJECTED' }),
      makeApplication({ needs_attention: true }),
      makeApplication({ missing_document_count: 2 }),
      makeApplication({}),
    ];
    const counters = computeSummaryCounters(applications);
    expect(counters.reduce((sum, c) => sum + c.count, 0)).toBe(5);
  });
});

describe('ValidationQueueSummary', () => {
  it('renders a card per bucket with its count and label', () => {
    render(
      <ValidationQueueSummary
        applications={[
          makeApplication({ status: 'APPROVED' }),
          makeApplication({ missing_document_count: 2 }),
        ]}
      />
    );

    expect(screen.getByLabelText('Completed')).toHaveTextContent('1');
    expect(screen.getByLabelText('Missing documents')).toHaveTextContent('1');
    expect(screen.getByLabelText('Pending')).toHaveTextContent('0');
    expect(screen.getByLabelText('Needs attention')).toHaveTextContent('0');
    expect(screen.getByLabelText('Rejected')).toHaveTextContent('0');
  });
});
