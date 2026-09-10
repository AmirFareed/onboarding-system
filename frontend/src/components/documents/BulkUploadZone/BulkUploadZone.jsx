import { useRef, useState } from 'react';
import { UploadCloud } from 'lucide-react';
import styles from './BulkUploadZone.module.css';

/**
 * A drag-and-drop zone for uploading the combined onboarding PDF.
 *
 * @param {object} props
 * @param {Function} props.onUpload Called with the selected File object.
 * @param {object|null} props.pending Bulk upload pending state (phase, progress).
 */
function BulkUploadZone({ onUpload, pending }) {
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.type === 'application/pdf') {
        onUpload(file);
      } else {
        alert('Please upload a valid PDF file.');
      }
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (file.type === 'application/pdf') {
        onUpload(file);
      } else {
        alert('Please upload a valid PDF file.');
      }
    }
  };

  const triggerPicker = () => {
    if (!pending && fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  };

  return (
    <div
      className={`${styles.container} ${dragActive ? styles.dragActive : ''}`}
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={triggerPicker}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          triggerPicker();
        }
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        hidden
        onChange={handleChange}
        tabIndex={-1}
      />

      <div className={styles.iconWrap} aria-hidden="true">
        <UploadCloud size={32} />
      </div>
      <h3 className={styles.title}>Upload Combined PDF</h3>
      <p className={styles.subtitle}>
        Drag and drop your complete onboarding package here, or click to browse. We will automatically split and categorize the documents.
      </p>

      {pending && (
        <div className={styles.progressOverlay}>
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{ width: `${pending.progress}%` }}
            />
          </div>
          <span className={styles.progressText}>
            {pending.phase === 'upload' ? `Uploading... ${pending.progress}%` : 'Processing...'}
          </span>
        </div>
      )}
    </div>
  );
}

export default BulkUploadZone;
