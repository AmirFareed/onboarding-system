import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import QuickActions from '../../../components/dashboard/QuickActions/QuickActions';

const { useAuth } = vi.hoisted(() => ({
  useAuth: vi.fn(),
}));

vi.mock('../../../hooks/useAuth', () => ({ useAuth }));

const NEW_APPLICATION = /^New Application/i;
const VIEW_APPLICATIONS = /^View Applications/i;
const VALIDATION = /^Open Validation(?! Report)/i;
const VALIDATION_REPORT = /^Open Validation Report/i;
const HUMAN_REVIEW = /^Open Human Review/i;
const PROCESSING = /^Processing/i;
const APPLICATION_HISTORY = /^Application History/i;
const PERFORMANCE = /^Performance/i;

function renderActions(role) {
  useAuth.mockReturnValue({ user: { role } });
  return render(
    <MemoryRouter>
      <QuickActions />
    </MemoryRouter>
  );
}

function expectLink(name, href) {
  expect(screen.getByRole('link', { name })).toHaveAttribute('href', href);
}

function expectNoLink(name) {
  expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
}

describe('QuickActions', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('hides strict IT shortcuts from the Employee account', () => {
    renderActions('Verification Officer');
    expectLink(NEW_APPLICATION, '/applications/new');
    expectLink(VIEW_APPLICATIONS, '/applications');
    expectLink(VALIDATION, '/validation');
    expectLink(VALIDATION_REPORT, '/reports');
    expectLink(HUMAN_REVIEW, '/human-review');
    expectNoLink(APPLICATION_HISTORY);
    expectNoLink(PERFORMANCE);
  });

  it('shows intake, validation and processing shortcuts for an OPERATOR', () => {
    renderActions('OPERATOR');
    expectLink(NEW_APPLICATION, '/applications/new');
    expectLink(VIEW_APPLICATIONS, '/applications');
    expectLink(VALIDATION, '/validation');
    expectLink(PROCESSING, '/processing');
    expectNoLink(VALIDATION_REPORT);
    expectNoLink(HUMAN_REVIEW);
    expectNoLink(APPLICATION_HISTORY);
    expectNoLink(PERFORMANCE);
  });

  it('shows review and report shortcuts but no create action for a REVIEWER', () => {
    renderActions('REVIEWER');
    expectLink(VIEW_APPLICATIONS, '/applications');
    expectLink(VALIDATION_REPORT, '/reports');
    expectLink(HUMAN_REVIEW, '/human-review');
    expectLink(PROCESSING, '/processing');
    expectNoLink(NEW_APPLICATION);
    expectNoLink(VALIDATION);
    expectNoLink(APPLICATION_HISTORY);
    expectNoLink(PERFORMANCE);
  });

  it('shows monitoring, history and performance shortcuts for an IT user', () => {
    renderActions('IT');
    expectLink(VIEW_APPLICATIONS, '/applications');
    expectLink(PROCESSING, '/processing');
    expectLink(APPLICATION_HISTORY, '/application-history');
    expectLink(PERFORMANCE, '/performance');
    expectNoLink(NEW_APPLICATION);
    expectNoLink(VALIDATION);
    expectNoLink(VALIDATION_REPORT);
    expectNoLink(HUMAN_REVIEW);
  });

  it('falls back to the OPERATOR shortcut set when no role is known', () => {
    useAuth.mockReturnValue({ user: null });
    render(
      <MemoryRouter>
        <QuickActions />
      </MemoryRouter>
    );
    expectLink(NEW_APPLICATION, '/applications/new');
    expectLink(VALIDATION, '/validation');
    expectNoLink(VALIDATION_REPORT);
    expectNoLink(APPLICATION_HISTORY);
    expectNoLink(PERFORMANCE);
  });
});
