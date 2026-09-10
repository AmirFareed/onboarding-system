import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import ApplicationCard from '../../components/applications/ApplicationCard/ApplicationCard';
import { useToast } from '../../components/common/Toast/ToastContext';
import { useApplications } from '../../hooks/useApplications';
import styles from './CreateApplicationPage.module.css';

/**
 * Create New Application page.
 *
 * Submits the form through the applications hook and navigates to the new
 * application's details page on success. Errors surface as toasts.
 */
function CreateApplicationPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { create } = useApplications();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (payload) => {
    setSubmitting(true);
    const result = await create(payload);
    setSubmitting(false);

    if (!result.ok) {
      toast.error(result.error);
      return;
    }

    toast.success(`Application #${result.application.id} created successfully.`);
    navigate(`/applications/${result.application.id}`);
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Create New Application</h2>
        <p className={styles.subtitle}>
          Fill in the details below to start a new document verification case.
        </p>
      </header>
      <ApplicationCard submitting={submitting} onSubmit={handleSubmit} />
    </div>
  );
}

export default CreateApplicationPage;
