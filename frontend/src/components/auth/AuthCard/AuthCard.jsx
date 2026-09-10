import Logo from '../../common/Logo/Logo';
import styles from './AuthCard.module.css';

/**
 * Shared shell for the authentication screens.
 *
 * An optional `background` layer renders behind the card (e.g. the login
 * video), so pages can decorate the page without restructuring the card.
 *
 * @param {object} props
 * @param {string} props.title Card heading.
 * @param {string} [props.subtitle] Card subheading.
 * @param {import('react').ReactNode} props.children Form content.
 * @param {import('react').ReactNode} [props.footer] Optional footer content.
 * @param {import('react').ReactNode} [props.background] Decorative layer
 *   rendered behind the card, or null.
 */
function AuthCard({ title, subtitle, children, footer, background = null }) {
  return (
    <div className={styles.wrap}>
      {background}
      <div className={styles.card}>
        <div className={styles.brand}>
          <Logo className={styles.logo} />
          <div className={styles.brandText}>
            <span className={styles.brandName}>FinTech</span>
            <span className={styles.brandSubtitle}>Onboarding Automation System</span>
          </div>
        </div>

        <h1 className={styles.title}>{title}</h1>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}

        <div className={styles.body}>{children}</div>

        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>
  );
}

export default AuthCard;
