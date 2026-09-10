import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from '../../components/common/Toast/ToastContext';
import HumanReviewPage from '../../pages/HumanReview/HumanReviewPage';

const { useHumanReview, useHumanReviewViewModel, useAuth } = vi.hoisted(() => ({
  useHumanReview: vi.fn(),
  useHumanReviewViewModel: vi.fn(),
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/useHumanReview', () => ({ useHumanReview }));
vi.mock('../../hooks/useHumanReviewViewModel', () => ({ useHumanReviewViewModel }));
vi.mock('../../hooks/useAuth', () => ({ useAuth }));
vi.mock('../../utils/preferences', () => ({
  getPreference: vi.fn(() => false),
}));

function reviewScreen(overrides) {
  return {
    application_id: 42,
    application: {
      application_id: 42,
      status: 'PENDING_REVIEW',
      submitted_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-02T00:00:00Z',
      created_by: 'operator1',
    },
    report: {
      overall_status: 'REQUIRES_REVIEW',
      recommendations: [],
      rules: [],
      document_summary: [],
      completeness: null,
      extraction_summary: null,
      visual_detection_summary: null,
    },
    documents: [],
    fields: [
      {
        field_name: 'account_holder',
        document_id: 1,
        file_name: 'amc.pdf',
        extracted_value: 'SAMPLE AUTHORITY',
        normalized_value: 'SAMPLE AUTHORITY',
        confidence_score: 0.92,
        confidence_source: 'exact_match',
        verification_status: 'CONFIRMED',
        human_corrected_value: null,
        human_verified: false,
      },
    ],
    visual_detections: [],
    checklist: [],
    previous_review: null,
    ...overrides,
  };
}

function defaultViewModel(overrides) {
  return {
    applicationId: 42,
    application: {
      application_id: 42,
      status: 'PENDING_REVIEW',
      submitted_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-02T00:00:00Z',
      created_by: 'operator1',
    },
    summary: {
      totalChecks: 0,
      passed: 0,
      actualFailures: 0,
      warnings: 0,
      pending: 0,
      notVerifiable: 0,
    },
    fields: { total: 1, verified: 1, needsReview: 0, progress: 100 },
    documents: [],
    visual: {
      signatures: { present: 0, missing: 0, pending: 0, notVerifiable: 0 },
      stamps: { present: 0, missing: 0, pending: 0, notVerifiable: 0 },
    },
    attention: [],
    ruleGroups: [],
    completeness: null,
    missingDocTypes: new Set(),
    missingDocTypesList: [],
    checklistRequirements: [],
    checklistGroups: [],
    approvalBlocking: { blocked: false, failures: 0, missingDocs: 0, uncheckedActionable: 0, reasons: [] },
    recommendations: [],
    requestableDocTypes: [],
    ...overrides,
  };
}

const baseHookValue = {
  applications: [{ id: 42, name: 'Test Org', status: 'PENDING_REVIEW' }],
  appsLoading: false,
  appsError: null,
  statusFilter: 'PENDING_REVIEW',
  onStatusChange: vi.fn(),
  selectedId: 42,
  onSelect: vi.fn(),
  reviewScreen: reviewScreen(),
  history: [],
  loading: false,
  error: null,
  submitting: false,
  submitError: null,
  submit: vi.fn(),
  alreadyReviewed: false,
  onRefresh: vi.fn(),
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <HumanReviewPage />
      </ToastProvider>
    </MemoryRouter>
  );
}

describe('HumanReviewPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('prompts for an application when none is selected', () => {
    useHumanReview.mockReturnValue({ ...baseHookValue, selectedId: null, reviewScreen: null });
    useHumanReviewViewModel.mockReturnValue(null);
    useAuth.mockReturnValue({ user: { name: 'Reviewer One' } });

    renderPage();

    expect(screen.getByText(/choose an application above/i)).toBeInTheDocument();
    expect(screen.queryByText('Extracted Fields')).not.toBeInTheDocument();
  });

  it('does not render the review sections while loading', () => {
    useHumanReview.mockReturnValue({ ...baseHookValue, loading: true, reviewScreen: null });
    useHumanReviewViewModel.mockReturnValue(null);
    useAuth.mockReturnValue({ user: { name: 'Reviewer One' } });

    renderPage();

    expect(screen.queryByText('Extracted Fields')).not.toBeInTheDocument();
  });

  it('shows the error state and retries via onRefresh', () => {
    const onRefresh = vi.fn();
    useHumanReview.mockReturnValue({
      ...baseHookValue,
      error: 'Network error',
      reviewScreen: null,
      onRefresh,
    });
    useHumanReviewViewModel.mockReturnValue(null);
    useAuth.mockReturnValue({ user: { name: 'Reviewer One' } });

    renderPage();

    expect(screen.getByText(/network error/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRefresh).toHaveBeenCalled();
  });

  it('renders extracted fields from the fetched review screen', () => {
    useHumanReview.mockReturnValue(baseHookValue);
    useHumanReviewViewModel.mockReturnValue(defaultViewModel());
    useAuth.mockReturnValue({ user: { name: 'Reviewer One' } });

    renderPage();

    expect(screen.getByText('Extracted Fields')).toBeInTheDocument();
    expect(screen.getByText('Account Holder')).toBeInTheDocument();
    expect(screen.getAllByText('SAMPLE AUTHORITY').length).toBeGreaterThan(0);
  });

  it('submits a CORRECT decision with the field correction in the payload', () => {
    const submit = vi.fn().mockResolvedValue({ review_id: 1 });
    useHumanReview.mockReturnValue({ ...baseHookValue, submit });
    useHumanReviewViewModel.mockReturnValue(defaultViewModel());
    useAuth.mockReturnValue({ user: { name: 'Reviewer One' } });

    renderPage();

    // Start a correction on the one extracted field and change its value.
    fireEvent.click(screen.getByRole('button', { name: 'Correct' }));
    fireEvent.change(screen.getByLabelText(/corrected value/i), {
      target: { value: 'CORRECTED AUTHORITY' },
    });

    // Choose the CORRECT decision and submit.
    fireEvent.click(screen.getByRole('radio', { name: /correct/i }));
    fireEvent.click(screen.getByRole('button', { name: /submit correction/i }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        decision: 'CORRECT',
        reviewer_name: 'Reviewer One',
        corrections: [
          {
            field_name: 'account_holder',
            document_id: 1,
            corrected_value: 'CORRECTED AUTHORITY',
            reason: null,
          },
        ],
      })
    );
  });

  it('shows the read-only banner and review history instead of the decision form once already reviewed', () => {
    useHumanReview.mockReturnValue({
      ...baseHookValue,
      alreadyReviewed: true,
      reviewScreen: reviewScreen({
        previous_review: {
          review_id: 7,
          application_id: 42,
          decision: 'APPROVE',
          reviewer_name: 'Reviewer One',
          reviewed_at: '2026-08-03T00:00:00Z',
          checklist_checked: 0,
          checklist_total: 0,
          corrections: [],
        },
      }),
      history: [
        {
          review_id: 7,
          application_id: 42,
          decision: 'APPROVE',
          reviewer_name: 'Reviewer One',
          reviewed_at: '2026-08-03T00:00:00Z',
          checklist_checked: 0,
          checklist_total: 0,
          corrections: [],
        },
      ],
    });
    useHumanReviewViewModel.mockReturnValue(defaultViewModel());
    useAuth.mockReturnValue({ user: { name: 'Reviewer One' } });

    renderPage();

    expect(screen.getByText(/already been finally reviewed/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit approval/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit correction/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirm rejection/i })).not.toBeInTheDocument();
    expect(screen.getByText('Review History')).toBeInTheDocument();
  });

  it('displays NOT_VERIFIABLE count in checklist group headers', () => {
    const checklistReqs = [
      {
        item_name: 'Authority Letter signature confirmed',
        itemName: 'Authority Letter signature confirmed',
        label: 'Authority Letter signature confirmed',
        is_checked: false,
        semanticStatus: 'ACTIONABLE',
        group: 'signatures',
        groupLabel: 'Signatures',
      },
      {
        item_name: 'Account Maintenance Certificate signature confirmed',
        itemName: 'Account Maintenance Certificate signature confirmed',
        label: 'Account Maintenance Certificate signature confirmed',
        is_checked: false,
        semanticStatus: 'ACTIONABLE',
        group: 'signatures',
        groupLabel: 'Signatures',
      },
      {
        item_name: 'Account Maintenance Certificate stamp confirmed',
        itemName: 'Account Maintenance Certificate stamp confirmed',
        label: 'Account Maintenance Certificate stamp confirmed',
        is_checked: false,
        semanticStatus: 'NOT_VERIFIABLE',
        group: 'stamps',
        groupLabel: 'Stamps',
      },
      {
        item_name: '1-Link Application stamp confirmed',
        itemName: '1-Link Application stamp confirmed',
        label: '1-Link Application stamp confirmed',
        is_checked: false,
        semanticStatus: 'NOT_VERIFIABLE',
        group: 'stamps',
        groupLabel: 'Stamps',
      },
    ];

    const vm = defaultViewModel({
      checklistRequirements: checklistReqs,
      checklistGroups: [
        { key: 'signatures', label: 'Signatures', items: checklistReqs.slice(0, 2), actionableCount: 2, confirmedCount: 0 },
        { key: 'stamps', label: 'Stamps', items: checklistReqs.slice(2), actionableCount: 0, confirmedCount: 0 },
      ],
    });

    useHumanReview.mockReturnValue({
      ...baseHookValue,
      reviewScreen: reviewScreen({
        checklist: checklistReqs.map((r) => ({
          item_name: r.item_name,
          is_checked: false,
        })),
      }),
    });
    useHumanReviewViewModel.mockReturnValue(vm);
    useAuth.mockReturnValue({ user: { name: 'Reviewer One' } });

    renderPage();

    expect(screen.getByText('Signatures')).toBeInTheDocument();
    expect(screen.getByText('Stamps')).toBeInTheDocument();

    // Signatures group: 0 / 2 actionable verified, no NV
    expect(screen.getByText('0 / 2 actionable verified')).toBeInTheDocument();

    // Stamps group: 0 / 0 actionable verified · 2 not verifiable
    expect(screen.getByText(/0 \/ 0 actionable verified · 2 not verifiable/)).toBeInTheDocument();
  });
});
