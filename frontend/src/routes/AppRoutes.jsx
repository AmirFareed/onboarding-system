import { Navigate, Route, Routes } from 'react-router-dom';

import RoleRoute from '../auth/RoleRoute';
import ProtectedLayout from '../components/layout/ProtectedLayout/ProtectedLayout';
import { ADMIN_NAV_ITEMS, INTERNAL_ROUTES, NAV_ITEMS } from '../data/navigation';
import {
  canAccessHumanReview,
  canAccessValidationReport,
  canUploadDocuments,
} from '../utils/permissions';
import ApplicationDetailsPage from '../pages/ApplicationDetails/ApplicationDetailsPage';
import ApplicationHistoryPage from '../pages/ApplicationHistory/ApplicationHistoryPage';
import ApplicationsPage from '../pages/Applications/ApplicationsPage';
import BatchUploadPage from '../pages/BatchUpload/BatchUploadPage';
import CreateApplicationPage from '../pages/CreateApplication/CreateApplicationPage';
import Dashboard from '../pages/Dashboard/Dashboard';
import HumanReviewPage from '../pages/HumanReview/HumanReviewPage';
import LoginPage from '../pages/Login/LoginPage';
import PerformancePage from '../pages/Performance/PerformancePage';
import PlaceholderPage from '../pages/Placeholder/PlaceholderPage';
import ProcessingPage from '../pages/Processing/ProcessingPage';
import ReportEditPage from '../pages/ReportEdit/ReportEditPage';
import SettingsPage from '../pages/Settings/SettingsPage';
import SystemLogsPage from '../pages/SystemLogs/SystemLogsPage';
import UploadDocumentsPage from '../pages/UploadDocuments/UploadDocumentsPage';
import ValidationPage from '../pages/Validation/ValidationPage';
import ValidationReportPage from '../pages/ValidationReport/ValidationReportPage';
import VerificationPage from '../pages/Verification/VerificationPage';

/**
 * Application route table.
 *
 * The applications module owns the list, create, details and upload pages.
 * The Validation, Validation Report, Human Review, Application History,
 * Performance and System Logs pages are real business workflows: Validation
 * reviews business-level completeness and drives the operator actions,
 * Validation Report shows the verification report, Human Review records the
 * final decision, and Application History / Performance / System Logs
 * (IT-only) give the IT team a business-facing lifecycle, timing and audit
 * view. Every other sidebar entry
 * resolves to the shared PlaceholderPage so no path returns a 404 and the
 * sidebar active state matches the route. Internal processing routes stay
 * reachable as placeholders but are not exposed in the sidebar. Admin/IT-only
 * routes (Feedback, Continuous Learning) are not sidebar entries either; they
 * are reached from the Settings page. Unknown URLs are redirected to the
 * dashboard.
 */
const PLACEHOLDER_ITEMS = [
  ...NAV_ITEMS.filter(
    ({ id }) =>
      !['dashboard', 'applications', 'processing', 'settings', 'validation', 'human-review', 'reports', 'application-history', 'performance', 'system-logs'].includes(id)
  ),
  ...ADMIN_NAV_ITEMS,
  ...INTERNAL_ROUTES,
];

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<ProtectedLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="applications" element={<ApplicationsPage />} />
        <Route
          path="applications/new"
          element={
            <RoleRoute canAccess={canUploadDocuments}>
              <CreateApplicationPage />
            </RoleRoute>
          }
        />
        <Route
          path="applications/batch-upload"
          element={
            <RoleRoute canAccess={canUploadDocuments}>
              <BatchUploadPage />
            </RoleRoute>
          }
        />
        <Route path="applications/:applicationId/upload" element={<UploadDocumentsPage />} />
        <Route path="applications/:applicationId/verification" element={<VerificationPage />} />
        <Route path="applications/:applicationId" element={<ApplicationDetailsPage />} />
        <Route path="processing" element={<ProcessingPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="application-history" element={<ApplicationHistoryPage />} />
        <Route path="performance" element={<PerformancePage />} />
        <Route path="system-logs" element={<SystemLogsPage />} />
        <Route
          path="reports"
          element={
            <RoleRoute canAccess={canAccessValidationReport}>
              <ValidationReportPage />
            </RoleRoute>
          }
        />
        <Route
          path="applications/:applicationId/report-edit"
          element={
            <RoleRoute canAccess={canAccessValidationReport}>
              <ReportEditPage />
            </RoleRoute>
          }
        />
        <Route
          path="human-review"
          element={
            <RoleRoute canAccess={canAccessHumanReview}>
              <HumanReviewPage />
            </RoleRoute>
          }
        />
        <Route path="validation" element={<ValidationPage />} />
        {PLACEHOLDER_ITEMS.map(({ id, label, path }) => (
          <Route
            key={id}
            path={path}
            element={
              <PlaceholderPage
                title={label}
                description={`The ${label} module is coming in a future phase.`}
              />
            }
          />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default AppRoutes;
