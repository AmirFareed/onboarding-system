import { Navigate, useLocation } from 'react-router-dom';

import LoadingScreen from '../components/auth/LoadingScreen/LoadingScreen';
import { useAuth } from '../hooks/useAuth';

function ProtectedRoute({ children }) {
  const { authenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <LoadingScreen />;
  }
  if (!authenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

export default ProtectedRoute;
