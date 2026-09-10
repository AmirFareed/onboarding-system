import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

import ApplicationRow from '../ApplicationRow/ApplicationRow';
import styles from './ApplicationTable.module.css';

/**
 * Sort-direction indicator for one column header.
 *
 * Module-level (not defined inside ApplicationTable) so React treats it as
 * a stable component type across renders instead of remounting it on every
 * render of the table.
 *
 * @param {object} props
 * @param {string} props.column This icon's column key.
 * @param {string} props.sortKey Currently active sort field.
 * @param {'asc'|'desc'} props.sortDir Current sort direction.
 */
function SortIcon({ column, sortKey, sortDir }) {
  if (column !== sortKey) {
    return <ArrowUpDown aria-hidden="true" />;
  }
  return sortDir === 'asc' ? <ArrowUp aria-hidden="true" /> : <ArrowDown aria-hidden="true" />;
}

/**
 * Table of applications with sortable columns.
 *
 * Renders a full table on desktop and collapses each row into a card on small
 * screens (see ApplicationRow). Column headers toggle sort order through
 * `onSortChange`; the active column reports its direction via `aria-sort`.
 *
 * @param {object} props
 * @param {Array<object>} props.applications Applications to display.
 * @param {string} props.sortKey Currently active sort field.
 * @param {'asc'|'desc'} props.sortDir Current sort direction.
 * @param {Function} props.onSortChange Callback with `(key, direction)`.
 */
function ApplicationTable({ applications, sortKey, sortDir, onSortChange }) {
  const toggleSort = (key) => {
    if (key === sortKey) {
      onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc');
      return;
    }
    onSortChange(key, 'desc');
  };

  const ariaSortFor = (key) => {
    if (key !== sortKey) {
      return 'none';
    }
    return sortDir === 'asc' ? 'ascending' : 'descending';
  };

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col" aria-sort={ariaSortFor('id')}>
              <button
                type="button"
                className={styles.sortButton}
                onClick={() => toggleSort('id')}
              >
                ID
                <SortIcon column="id" sortKey={sortKey} sortDir={sortDir} />
              </button>
            </th>
            <th scope="col">Name</th>
            <th scope="col">Status</th>
            <th scope="col" aria-sort={ariaSortFor('submitted_at')}>
              <button
                type="button"
                className={styles.sortButton}
                onClick={() => toggleSort('submitted_at')}
              >
                Submission Date
                <SortIcon column="submitted_at" sortKey={sortKey} sortDir={sortDir} />
              </button>
            </th>
            <th scope="col" aria-sort={ariaSortFor('updated_at')}>
              <button
                type="button"
                className={styles.sortButton}
                onClick={() => toggleSort('updated_at')}
              >
                Last Updated
                <SortIcon column="updated_at" sortKey={sortKey} sortDir={sortDir} />
              </button>
            </th>
            <th scope="col">Created By</th>
            <th scope="col" className={styles.actionsHeader}>
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {applications.map((application) => (
            <ApplicationRow key={application.id} application={application} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default ApplicationTable;
