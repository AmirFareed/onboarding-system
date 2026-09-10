import Logo from '../../common/Logo/Logo';
import Spinner from '../../common/Spinner/Spinner';
import styles from './LoadingScreen.module.css';

function LoadingScreen() {
  return (
    <div className={styles.screen} role="status" aria-busy="true" aria-live="polite">
      <Logo className={styles.logo} />
      <Spinner size="medium" />
      <span className={styles.label}>Loading secure portal...</span>
    </div>
  );
}

export default LoadingScreen;
