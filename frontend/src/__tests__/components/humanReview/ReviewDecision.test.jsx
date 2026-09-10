import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ReviewDecision from '../../../components/humanReview/ReviewDecision/ReviewDecision';

const defaultApprovalBlocking = {
  blocked: false,
  failures: 0,
  missingDocs: 0,
  uncheckedActionable: 0,
  reasons: [],
};

function renderDecision(overrides = {}) {
  const onSubmit = vi.fn();
  render(
    <ReviewDecision
      reviewerName="Jane Reviewer"
      decision=""
      onDecisionChange={() => {}}
      comments=""
      onCommentsChange={() => {}}
      rejectionReason=""
      onRejectionReasonChange={() => {}}
      checklist={[]}
      corrections={[]}
      approvalBlocking={defaultApprovalBlocking}
      requestableDocTypes={[]}
      onRequestMissingDocs={() => {}}
      submitting={false}
      readOnly={false}
      submitError={null}
      onSubmit={onSubmit}
      condition=""
      onConditionChange={() => {}}
      dueDate=""
      onDueDateChange={() => {}}
      additionalComments=""
      onAdditionalCommentsChange={() => {}}
      {...overrides}
    />
  );
  return { onSubmit };
}

describe('ReviewDecision — approval gating', () => {
  it('shows blocking error when approval is blocked', () => {
    renderDecision({
      decision: 'APPROVE',
      approvalBlocking: {
        blocked: true,
        failures: 1,
        missingDocs: 2,
        uncheckedActionable: 3,
        reasons: [],
      },
    });

    expect(screen.getByText('Approval Blocked')).toBeInTheDocument();
    expect(screen.getByText('1 validation failure')).toBeInTheDocument();
    expect(screen.getByText('2 missing required documents')).toBeInTheDocument();
    expect(screen.getByText('3 actionable review items not confirmed')).toBeInTheDocument();
  });

  it('allows APPROVE when not blocked', () => {
    const { onSubmit } = renderDecision({ decision: 'APPROVE' });

    const submitButton = screen.getByRole('button', { name: /submit approval/i });
    expect(submitButton).not.toBeDisabled();

    fireEvent.click(submitButton);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('shows Request Missing Documents button when documents are missing', () => {
    renderDecision({
      requestableDocTypes: ['AUTHORITY_LETTER', 'BILATERAL_AGREEMENT'],
    });

    expect(
      screen.getByRole('button', { name: /Request Missing Documents \(2\)/i })
    ).toBeInTheDocument();
  });

  it('shows corrections summary when corrections exist', () => {
    renderDecision({
      corrections: [
        { document_id: 1, field_name: 'account_number', corrected_value: '12345', reason: '' },
      ],
    });

    expect(screen.getByText('1 field correction recorded')).toBeInTheDocument();
  });
});

describe('ReviewDecision — dynamic submit labels', () => {
  it('shows "Submit Approval" for APPROVE', () => {
    renderDecision({ decision: 'APPROVE' });
    expect(screen.getByRole('button', { name: /submit approval/i })).toBeInTheDocument();
  });

  it('shows "Submit Correction" for CORRECT', () => {
    renderDecision({
      decision: 'CORRECT',
      corrections: [{ document_id: 1, field_name: 'field', corrected_value: 'val', reason: '' }],
    });
    expect(screen.getByRole('button', { name: /submit correction/i })).toBeInTheDocument();
  });

  it('shows "Confirm Rejection" for REJECT', () => {
    renderDecision({ decision: 'REJECT', rejectionReason: 'Bad docs' });
    expect(screen.getByRole('button', { name: /confirm rejection/i })).toBeInTheDocument();
  });

  it('shows "Confirm Conditional Approval" for CONDITIONAL_APPROVE', () => {
    renderDecision({ decision: 'CONDITIONAL_APPROVE', condition: 'Submit missing docs' });
    expect(
      screen.getByRole('button', { name: /confirm conditional approval/i })
    ).toBeInTheDocument();
  });
});

describe('ReviewDecision — Conditional Approval', () => {
  it('renders the Conditional Approval option', () => {
    renderDecision();
    expect(screen.getByText('Conditional Approval')).toBeInTheDocument();
    expect(
      screen.getByText('Approves subject to explicitly recorded conditions. Bypasses normal approval blocking.')
    ).toBeInTheDocument();
  });

  it('shows condition form when Conditional Approval is selected', () => {
    renderDecision({ decision: 'CONDITIONAL_APPROVE' });
    expect(screen.getByText('Condition / Required Action (required)')).toBeInTheDocument();
    expect(screen.getByText('Due Date (optional)')).toBeInTheDocument();
    expect(screen.getByText('Additional Comments (optional)')).toBeInTheDocument();
  });

  it('requires condition text', () => {
    renderDecision({ decision: 'CONDITIONAL_APPROVE', condition: '' });
    expect(
      screen.getByText(/A condition or required action is mandatory/i)
    ).toBeInTheDocument();
  });

  it('shows API limitation message when condition is provided', () => {
    renderDecision({ decision: 'CONDITIONAL_APPROVE', condition: 'Submit docs' });
    expect(
      screen.getByText(/Conditional Approval is not yet supported by the backend API/i)
    ).toBeInTheDocument();
  });

  it('does not show blocking error when Conditional Approval is selected', () => {
    renderDecision({
      decision: 'CONDITIONAL_APPROVE',
      condition: 'Submit docs',
      approvalBlocking: {
        blocked: true,
        failures: 1,
        missingDocs: 2,
        uncheckedActionable: 3,
        reasons: [],
      },
    });
    expect(screen.queryByText('Approval Blocked')).not.toBeInTheDocument();
  });

  it('submit button is disabled due to API limitation', () => {
    renderDecision({ decision: 'CONDITIONAL_APPROVE', condition: 'Submit docs' });
    const submitButton = screen.getByRole('button', { name: /confirm conditional approval/i });
    expect(submitButton).toBeDisabled();
  });
});

describe('ReviewDecision — blocking message wording', () => {
  it('uses "actionable review items not confirmed" wording', () => {
    renderDecision({
      decision: 'APPROVE',
      approvalBlocking: {
        blocked: true,
        failures: 0,
        missingDocs: 0,
        uncheckedActionable: 5,
        reasons: [],
      },
    });
    expect(screen.getByText('5 actionable review items not confirmed')).toBeInTheDocument();
  });

  it('combines failures and unchecked items with "and"', () => {
    renderDecision({
      decision: 'APPROVE',
      approvalBlocking: {
        blocked: true,
        failures: 1,
        missingDocs: 0,
        uncheckedActionable: 3,
        reasons: [],
      },
    });
    expect(
      screen.getByText(/1 validation failure and 3 actionable review items not confirmed/)
    ).toBeInTheDocument();
  });
});
