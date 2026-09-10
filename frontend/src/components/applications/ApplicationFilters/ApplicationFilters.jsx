import { APPLICATION_STATUSES } from '../../../data/statuses';
import styles from './ApplicationFilters.module.css';

/**
 * Status filter control for the applications list.
 *
 * Renders an "All" option plus every application status in the shared
 * catalogue. Stacks vertically below the search bar on small screens.
 *
 * @param {object} props
 * @param {string} props.value Currently selected status value ('' for all).
 * @param {Function} props.onChange Callback with the next status value.
 * @param {string} [props.id] Optional id for label association.
 */
function ApplicationFilters({ value, onChange, id }) {
  return (
    <label className={styles.filter} htmlFor={id}>
      <span className={styles.label}>Status</span>
      <select
        id={id}
        className={styles.select}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Filter applications by status"
      >
        <option value="">All</option>
        {APPLICATION_STATUSES.map(({ value: statusValue, label }) => (
          <option key={statusValue} value={statusValue}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default ApplicationFilters;
