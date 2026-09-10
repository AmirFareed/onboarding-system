import { useState } from 'react';

import video from '../../../assets/8387491-uhd_3840_2160_30fps.mp4';
import { usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';
import styles from './LoginVideoBackground.module.css';

/**
 * Full-viewport background layer for the login page.
 *
 * Renders the local FinTech promo loop behind the opaque auth card. The video
 * is purely decorative: it is muted, loops silently, has no controls and is
 * excluded from the accessibility tree and tab order. It never plays when the
 * user has requested reduced motion, and a themed gradient (also used as the
 * fallback while the asset loads or if it fails) keeps the page on-brand.
 *
 * The layer is fixed in place behind the card and swallows no pointer events,
 * so the login form is unaffected.
 */
function LoginVideoBackground() {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [failed, setFailed] = useState(false);

  const showVideo = !prefersReducedMotion && !failed;

  return (
    <div className={styles.container} aria-hidden="true">
      {showVideo && (
        <video
          className={styles.video}
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          tabIndex={-1}
          disablePictureInPicture
          onError={() => setFailed(true)}
        >
          <source src={video} type="video/mp4" />
        </video>
      )}
      <div className={styles.overlay} aria-hidden="true" />
    </div>
  );
}

export default LoginVideoBackground;
