import styles from './ApplicationSkeleton.module.css';

/**
 * Shimmer placeholder rows that mirror the applications table while data is
 * loading, so the page never flashes a blank screen.
 */
export function ApplicationTableSkeleton() {
  return (
    <div className={styles.tableWrap} aria-hidden="true">
      <div className={styles.headerRow}>
        <div className={`${styles.bar} ${styles.wide}`} />
        <div className={`${styles.bar} ${styles.short}`} />
        <div className={`${styles.bar} ${styles.medium}`} />
        <div className={`${styles.bar} ${styles.medium}`} />
        <div className={`${styles.bar} ${styles.medium}`} />
        <div className={`${styles.bar} ${styles.tiny}`} />
      </div>
      {Array.from({ length: 6 }, (_, index) => (
        <div className={styles.row} key={index}>
          <div className={`${styles.bar} ${styles.short}`} />
          <div className={`${styles.bar} ${styles.xshort}`} />
          <div className={`${styles.bar} ${styles.medium}`} />
          <div className={`${styles.bar} ${styles.medium}`} />
          <div className={`${styles.bar} ${styles.medium}`} />
          <div className={`${styles.bar} ${styles.tiny}`} />
        </div>
      ))}
    </div>
  );
}

/**
 * Shimmer card used while an application's details are loading.
 */
export function ApplicationCardSkeleton() {
  return (
    <div className={styles.card} aria-hidden="true">
      <div className={styles.cardTitleBar} />
      <div className={styles.grid}>
        {Array.from({ length: 4 }, (_, index) => (
          <div className={styles.field} key={index}>
            <div className={`${styles.bar} ${styles.xshort}`} />
            <div className={`${styles.bar} ${styles.short}`} />
          </div>
        ))}
      </div>
      <div className={styles.cardTitleBar} />
      <div className={`${styles.bar} ${styles.full}`} />
      <div className={`${styles.bar} ${styles.full}`} />
    </div>
  );
}
