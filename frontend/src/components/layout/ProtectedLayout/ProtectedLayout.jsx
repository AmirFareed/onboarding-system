import SessionTimeoutModal from '../../auth/SessionTimeoutModal/SessionTimeoutModal';
import ProtectedRoute from '../../../auth/ProtectedRoute';
import DashboardLayout from '../DashboardLayout/DashboardLayout';
import { ApplicationsProvider } from '../../../store/ApplicationsContext';
import { BatchUploadProvider } from '../../../store/BatchUploadContext';

function ProtectedLayout() {
  return (
    <ProtectedRoute>
      <ApplicationsProvider>
        <BatchUploadProvider>
          <DashboardLayout />
          <SessionTimeoutModal />
        </BatchUploadProvider>
      </ApplicationsProvider>
    </ProtectedRoute>
  );
}

export default ProtectedLayout;
