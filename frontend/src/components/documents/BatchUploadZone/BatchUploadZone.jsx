import { useRef, useState } from 'react';
import { Files } from 'lucide-react';
import styles from './BatchUploadZone.module.css';

/**
 * A drag-and-drop zone for selecting many PDF files at once.
 *
 * Distinct from BulkUploadZone (single combined-PDF-per-application upload):
 * this one accepts an unbounded number of separate PDFs, each of which will
 * become its own application. Non-PDF files are filtered out by the caller
 * (BatchUploadContext.addFiles), not here -- this component's only job is
 * collecting the raw FileList/drop event and handing it up.
 *
 * @param {object} props
 * @param {Function} props.onFilesSelected Called with a FileList/File[].
 * @param {boolean} [props.disabled] Disables picking/dropping while true.
 */
function BatchUploadZone({ onFilesSelected, disabled = false }) {
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (disabled) {
      return;
    }
    if (event.type === 'dragenter' || event.type === 'dragover') {
      setDragActive(true);
    } else if (event.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    if (disabled) {
      return;
    }
    if (event.dataTransfer.files?.length) {
      onFilesSelected(event.dataTransfer.files);
    }
  };

  const handleChange = (event) => {
    if (event.target.files?.length) {
      onFilesSelected(event.target.files);
    }
    event.target.value = '';
  };

  const triggerPicker = () => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  return (
    <div
      className={`${styles.container} ${dragActive ? styles.dragActive : ''} ${disabled ? styles.disabled : ''}`}
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={triggerPicker}
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          triggerPicker();
        }
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        multiple
        hidden
        onChange={handleChange}
        tabIndex={-1}
        disabled={disabled}
      />

      <div className={styles.iconWrap} aria-hidden="true">
        <Files size={32} />
      </div>
      <h3 className={styles.title}>Upload Multiple PDFs</h3>
      <p className={styles.subtitle}>
        Drag and drop 30 or more PDF files here, or click to browse. Each file becomes its own
        application, automatically named from its filename.
      </p>
    </div>
  );
}

export default BatchUploadZone;
