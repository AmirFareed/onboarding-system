import AuthProvider from './auth/AuthProvider';
import { ToastProvider } from './components/common/Toast/ToastContext';
import AppRoutes from './routes/AppRoutes';
import { ThemeProvider } from './theme/ThemeProvider';

/**
 * Application root.
 *
 * Composes the global providers: theming (light/dark/system), authentication
 * (session restoration, login/logout) and toast notifications, in that order.
 * The theme provider sits outermost so the whole tree, including the login
 * screen, renders against the resolved palette.
 */
function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ToastProvider>
          <AppRoutes />
        </ToastProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
