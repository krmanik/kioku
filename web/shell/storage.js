// Linked in with --pre-js: keep /home/web_user (Anki's profiles,
// collections and media, see kioku_platform.documents_dir()) in IndexedDB.
// It is loaded before main() runs and saved whenever the page calls
// __kiokuPersist() (kioku-web.js: on a timer, when the page is hidden and
// after collection operations). The folder is a MEMFS mount synced with
// IDBFS's functions: mounted as IDBFS (even without autoPersist) the app
// trapped (`unreachable` in emscripten_futex_wait) once the profile opened;
// loading from main() through Asyncify broke Qt's event loop.
//
// Memory: an iPhone ends a tab that goes over its limit, and IDBFS's own
// sync handles every changed file at once (all of them structured-cloned
// into one transaction, or all read back together), on top of the garbage
// MEMFS leaves when a file grows. So files are synced a batch at a time,
// each transaction finished before the next, saved as exact-size copies,
// and MEMFS grows files 2x (a 30 MB file was copied ~30 times at 1.125x).
//
// Order: a save can stop anywhere (the tab is closed, the phone ends it, the
// quota runs out). Anki's media database (collection.media.db2) lists the
// files in collection.media/; saved ahead of a file it lists and reloaded
// without it, Anki takes the file as deleted and the next sync deletes it on
// AnkiWeb and every other device (issue #10). So a save writes
//   1. folders, so every saved file has its folder when loaded
//   2. media files (collection.media/, media.trash/), then their removals,
//      again until the media folders hold nothing unsaved
//   3. the media database, in the same task as the last check of step 2
//   4. everything else
// Stopped early, the saved media folder holds at most more than the database
// lists; Anki adds those files back on its next check. A SQLite file and its
// -wal/-shm/-journal always go in one transaction.
//
// Loading: if it fails, Kioku does not start and nothing is saved (started
// with part of the files, Anki would take the rest as deleted and a save
// would delete them from IndexedDB too).
if (typeof ENVIRONMENT_IS_PTHREAD === "undefined" || !ENVIRONMENT_IS_PTHREAD) {
  Module.preRun = [].concat(Module.preRun || [], () => {
    addRunDependency("kioku-storage");
    MEMFS.expandFileStorage = (node, newCapacity) => {
      const prev = node.contents ? node.contents.length : 0;
      if (prev >= newCapacity) return;
      newCapacity = Math.max(newCapacity, prev * 2, 256);
      const old = node.contents;
      node.contents = new Uint8Array(newCapacity);
      if (node.usedBytes > 0) node.contents.set(old.subarray(0, node.usedBytes), 0);
    };
    const root = FS.mount(MEMFS, {}, "/home/web_user");
    const mount = root.mount;
    let state = "idle";
    globalThis.__kiokuPersist = () => {
      if (state === "failed") return;
      if (state !== "idle") {
        state = "again";
        return;
      }
      state = "saving";
      const run = () =>
        kiokuSync(mount, false).then(
          () => (state === "again" ? ((state = "saving"), run()) : (state = "idle")),
          (err) => {
            console.error("Kioku: saving files failed", err);
            state = "idle";
          },
        );
      run();
    };
    kiokuSync(mount, true).then(
      () => removeRunDependency("kioku-storage"),
      (err) => {
        console.error("Kioku: loading saved files failed", err);
        state = "failed";
        kiokuLoadFailed(err);
      },
    );
  });
}

// bytes per IndexedDB transaction when saving; files per one when loading
var KIOKU_SAVE_BATCH = 8 * 1024 * 1024;
var KIOKU_LOAD_BATCH = 8;

function kiokuCall(fn, ...args) {
  return new Promise((ok, fail) => fn(...args, (err, value) => (err ? fail(err) : ok(value))));
}

function kiokuSync(mount, populate) {
  return populate ? kiokuLoadAll(mount) : kiokuSaveAll(mount);
}

async function kiokuLoadAll(mount) {
  const [local, remote] = await Promise.all([kiokuCall(IDBFS.getLocalSet, mount), kiokuCall(IDBFS.getRemoteSet, mount)]);
  const changed = Object.keys(remote.entries)
    .filter((key) => {
      const theirs = local.entries[key];
      return !theirs || remote.entries[key]["timestamp"].getTime() != theirs["timestamp"].getTime();
    })
    // directories before the files in them
    .sort();
  await kiokuLoad(remote.db, changed);
  // files before their directories
  for (const path of Object.keys(local.entries).filter((key) => !remote.entries[key]).sort().reverse()) {
    IDBFS.removeLocalEntry(path, () => {});
  }
}

var KIOKU_MEDIA = /\/(collection\.media|media\.trash)\//;
var KIOKU_MEDIA_DB = /\/collection\.media\.db[^/]*$/;

// a SQLite file with its -wal/-shm/-journal
function kiokuGroup(path) {
  return path && path.replace(/-(wal|shm|journal)$/, "");
}

function kiokuIsDir(path) {
  try {
    return FS.isDir(FS.stat(path).mode);
  } catch (e) {
    return false;
  }
}

// the order is explained at the top
async function kiokuSaveAll(mount) {
  const remote = await kiokuCall(IDBFS.getRemoteSet, mount);
  const db = remote.db;
  // timestamp of each saved path, kept up to date as transactions finish
  const saved = {};
  for (const key of Object.keys(remote.entries)) saved[key] = remote.entries[key]["timestamp"].getTime();
  // synchronous: IDBFS.getLocalSet only walks MEMFS
  const localSet = () => {
    let entries;
    IDBFS.getLocalSet(mount, (err, local) => {
      if (err) throw err;
      entries = local.entries;
    });
    return entries;
  };
  const changed = (local, test) =>
    Object.keys(local)
      .filter((key) => test(key) && saved[key] !== local[key]["timestamp"].getTime())
      .sort();
  const removed = (local, test) =>
    Object.keys(saved)
      .filter((key) => test(key) && !local[key])
      .sort()
      .reverse();

  let local = localSet();
  await kiokuWrite(db, changed(local, kiokuIsDir), saved);
  for (let round = 0; ; round++) {
    local = localSet();
    const files = changed(local, (key) => KIOKU_MEDIA.test(key) && !kiokuIsDir(key));
    const gone = removed(local, (key) => KIOKU_MEDIA.test(key));
    if (!files.length && !gone.length) break;
    // still changing (a long media sync): the database waits for the next save
    if (round === 10) return;
    await kiokuWrite(db, files.concat(gone), saved);
  }
  // no await between the check above and reading the database here
  const isMediaDb = (key) => KIOKU_MEDIA_DB.test(key);
  const mediaDb = changed(local, isMediaDb).concat(removed(local, isMediaDb)).sort();
  await kiokuWrite(db, mediaDb, saved, Infinity);

  local = localSet();
  const other = (key) => !KIOKU_MEDIA.test(key) && !isMediaDb(key);
  const rest = changed(local, (key) => other(key) && !kiokuIsDir(key))
    .concat(removed(local, other))
    .sort();
  await kiokuWrite(db, rest, saved);
}

// what IDBFS stores for a path, or null when it is gone
function kiokuEntry(path) {
  let stat;
  try {
    stat = FS.stat(path);
  } catch (e) {
    return null;
  }
  if (FS.isDir(stat.mode)) return { "timestamp": stat.mtime, "mode": stat.mode };
  if (!FS.isFile(stat.mode)) return null;
  const node = FS.lookupPath(path).node;
  // a structured clone copies the view's whole buffer, spare capacity
  // included: keep (and save) an exact-size copy instead
  let contents = MEMFS.getFileDataAsTypedArray(node);
  if (contents.byteLength !== contents.buffer.byteLength) contents = contents.slice();
  node.contents = contents;
  return { "timestamp": stat.mtime, "mode": stat.mode, "contents": contents };
}

// save (or, gone, delete) the paths in order, a transaction per
// KIOKU_SAVE_BATCH bytes, never splitting a SQLite file's group
async function kiokuWrite(db, paths, saved, batchBytes = KIOKU_SAVE_BATCH) {
  let batch = [];
  let bytes = 0;
  const flush = async () => {
    const entries = batch;
    batch = [];
    bytes = 0;
    if (!entries.length) return;
    await kiokuTransaction(db, "readwrite", (store) =>
      entries.forEach(([path, entry]) => (entry ? store.put(entry, path) : store.delete(path))),
    );
    for (const [path, entry] of entries) {
      if (entry) saved[path] = entry["timestamp"].getTime();
      else delete saved[path];
    }
  };
  for (let i = 0; i < paths.length; i++) {
    const entry = kiokuEntry(paths[i]);
    batch.push([paths[i], entry]);
    if (entry && entry["contents"]) bytes += entry["contents"].byteLength;
    if (bytes >= batchBytes && kiokuGroup(paths[i + 1]) !== kiokuGroup(paths[i])) await flush();
  }
  await flush();
}

// Kioku stays on its loading screen with a note; the saved files are left as
// they are, so a reload tries again
function kiokuLoadFailed(err) {
  const note = document.createElement("div");
  note.setAttribute("role", "alert");
  note.style.cssText =
    "position:fixed;inset:0;z-index:10;display:flex;align-items:center;justify-content:center;" +
    "padding:24px;background:#222;color:#eee;font:16px/1.5 system-ui,sans-serif;text-align:center";
  note.textContent =
    "Kioku couldn't load your saved collection, so it didn't start, and nothing was changed. " +
    "Reload the page to try again. (" + (err && err.message ? err.message : err) + ")";
  document.body.appendChild(note);
}

function kiokuTransaction(db, mode, fill) {
  return new Promise((ok, fail) => {
    const tx = db.transaction([IDBFS.DB_STORE_NAME], mode);
    tx.oncomplete = () => ok();
    tx.onerror = tx.onabort = (e) => {
      e.preventDefault();
      fail(tx.error || e.target.error);
    };
    fill(tx.objectStore(IDBFS.DB_STORE_NAME));
  });
}

async function kiokuLoad(db, paths) {
  for (let i = 0; i < paths.length; i += KIOKU_LOAD_BATCH) {
    const entries = [];
    await kiokuTransaction(db, "readonly", (store) =>
      paths.slice(i, i + KIOKU_LOAD_BATCH).forEach((path) => {
        store.get(path).onsuccess = (e) => entries.push([path, e.target.result]);
      }),
    );
    for (const [path, entry] of entries) {
      if (!entry) continue;
      // an older save may have stopped before a folder's entry
      if (!FS.isDir(entry["mode"])) FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
      await new Promise((ok, fail) => IDBFS.storeLocalEntry(path, entry, (err) => (err ? fail(err) : ok())));
    }
  }
}
