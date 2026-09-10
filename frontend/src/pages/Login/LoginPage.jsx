import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import AuthCard from '../../components/auth/AuthCard/AuthCard';
import LoadingScreen from '../../components/auth/LoadingScreen/LoadingScreen';
import LoginVideoBackground from '../../components/auth/LoginVideoBackground/LoginVideoBackground';
import PasswordField from '../../components/auth/PasswordField/PasswordField';
import Spinner from '../../components/common/Spinner/Spinner';
import { useAuth } from '../../hooks/useAuth';
import { getApiErrorMessage } from '../../utils/apiError';
import styles from './LoginPage.module.css';

function getLoginErrorMessage(error) {
  if (!error?.response) {
    if (error?.code === 'ECONNABORTED') {
      return 'The request timed out. Please try again.';
    }
    return 'Network unavailable. Check your connection and try again.';
  }
  const { status } = error.response;
  if (status === 401) {
    return 'Invalid employee credentials.';
  }
  if (status === 403) {
    return 'Your account does not have access to this portal.';
  }
  if (status === 429) {
    return 'Too many login attempts. Please try again later.';
  }
  if (status >= 500) {
    return 'Server unavailable. Please try again later.';
  }
  return getApiErrorMessage(error);
}

function LoginPage() {
  const { authenticated, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from ?? '/';

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return <LoadingScreen />;
  }
  if (authenticated) {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();

    const nextFieldErrors = {};
    if (!identifier.trim()) {
      nextFieldErrors.identifier = 'Enter your employee ID or email.';
    }
    if (!password) {
      nextFieldErrors.password = 'Enter your password.';
    }
    setFieldErrors(nextFieldErrors);
    setError('');
    if (Object.keys(nextFieldErrors).length > 0) {
      return;
    }

    setSubmitting(true);
    try {
      await login({ identifier: identifier.trim(), password, remember });
      navigate(from, { replace: true });
    } catch (err) {
      setError(getLoginErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthCard
      title="Sign In"
      subtitle="Secure Internal Employee Portal"
      background={<LoginVideoBackground />}
      footer={
        <p className={styles.notice}>
          Authorized finance personnel only. All activity is logged and monitored.
        </p>
      }
    >
      {error && (
        <div className={styles.banner} role="alert">
          {error}
        </div>
      )}

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="identifier">
            Employee ID or Email
          </label>
          <input
            id="identifier"
            type="text"
            autoComplete="username"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            aria-invalid={Boolean(fieldErrors.identifier)}
            aria-describedby={fieldErrors.identifier ? 'identifier-error' : undefined}
            className={`${styles.input} ${fieldErrors.identifier ? styles.invalid : ''}`}
          />
          {fieldErrors.identifier && (
            <p id="identifier-error" className={styles.fieldError} role="alert">
              {fieldErrors.identifier}
            </p>
          )}
        </div>

        <PasswordField
          id="password"
          label="Password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
        />

        <div className={styles.optionsRow}>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            <span>Remember this device</span>
          </label>
          <button className={styles.forgot} type="button" title="Password recovery is not available yet">
            Forgot password?
          </button>
        </div>

        <button className={styles.submit} type="submit" disabled={submitting}>
          {submitting && <Spinner size="small" />}
          {submitting ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </AuthCard>
  );
}

export default LoginPage;
