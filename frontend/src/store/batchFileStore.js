/**
 * IndexedDB-backed storage for the batch upload queue's actual file bytes,
 * keyed by each item's clientId.
 *
 * `BatchUploadContext`'s own STORAGE_KEY (localStorage) persists everything
 * about a queued item *except* its File -- a File's byte content cannot be
 * JSON-serialized. IndexedDB is the one browser storage mechanism that can
 * hold a Blob/File's actual bytes across a real page reload, so this module
 * exists specifically to let a queued-but-not-yet-uploaded file survive one,
 * instead of requiring the user to re-select it by hand.
 *
 * Every function here degrades gracefully (rejects, never throws
 * synchronously) when IndexedDB is unavailable -- private browsing, a
 * storage quota already exceeded, or (only in this project's own test
 * environment) jsdom, which does not implement IndexedDB at all -- so a
 * caller can always fall back to the pre-existing "this file needs to be
 * re-added by hand" behavior rather than crashing.
 */

const DB_NAME = 'onboarding-system-batch-files';
const DB_VERSION = 1;
const STORE_NAME = 'files';

function openDb() {
  if (typeof indexedDB === 'undefined') {
    return Promise.reject(new Error('IndexedDB is not available in this environment.'));
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE_NAME);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** Store a queued file's bytes under its clientId. */
export async function putFile(clientId, file) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).put(
      { blob: file, name: file.name, type: file.type, lastModified: file.lastModified },
      clientId
    );
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    db.close();
  });
}

/**
 * Retrieve a previously-stored file, reconstructed as a real File object, or
 * null if nothing is stored under this clientId (never stored, already
 * deleted, or a different browser/profile).
 */
export async function getFile(clientId) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const request = tx.objectStore(STORE_NAME).get(clientId);
    request.onsuccess = () => {
      const record = request.result;
      if (!record) {
        resolve(null);
        return;
      }
      resolve(
        new File([record.blob], record.name, {
          type: record.type,
          lastModified: record.lastModified,
        })
      );
    };
    request.onerror = () => reject(request.error);
    db.close();
  });
}

/** Remove one stored file -- called once it's no longer needed (removed from the queue, or the whole queue is cleared). */
export async function deleteFile(clientId) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).delete(clientId);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    db.close();
  });
}

/** Remove every stored file -- called when the whole queue is reset. */
export async function clearAllFiles() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    db.close();
  });
}
