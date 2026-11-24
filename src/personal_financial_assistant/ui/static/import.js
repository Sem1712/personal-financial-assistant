const POLL_INTERVAL = 1000;
const LEGACY_RUN_KEY = "pfa-pending-import";
const RUN_KEY_PREFIX = "pfa-pending-import:";
const INPUT_NOTICE = "Enter a non-empty local folder path without invalid characters and try again.";
const STORAGE_NOTICE = "Browser storage is unavailable. Enable it before using imports.";
const COUNT_LABELS = [
  ["files_seen", "Files seen"],
  ["files_processed", "Files processed"],
  ["files_unchanged", "Files unchanged"],
  ["rows_read", "Rows read"],
  ["transactions_added", "Transactions added"],
  ["transactions_updated", "Transactions updated"],
  ["observations_unchanged", "Observations unchanged"],
  ["unresolved_observations", "Unresolved observations"],
];

function validRun(run) {
  if (run === null) return true;
  if (!run || typeof run !== "object" || typeof run.id !== "string") return false;
  if (!["running", "succeeded", "no_files", "failed", "unknown"].includes(run.state)) {
    return false;
  }
  if (typeof run.started_at !== "string") return false;
  if (run.state === "running") return run.finished_at === null;
  if (typeof run.finished_at !== "string") return false;
  if (run.state === "succeeded" || run.state === "no_files") {
    return run.counts && COUNT_LABELS.every(
      ([key]) => Number.isSafeInteger(run.counts[key]) && run.counts[key] >= 0,
    );
  }
  if (run.state === "failed") {
    return run.error && typeof run.error.message === "string";
  }
  return true;
}

export function createImportView({ request, HttpError, setLocked, showImport }) {
  const form = document.querySelector("#import-form");
  const folder = document.querySelector("#import-folder");
  const start = document.querySelector("#import-start");
  const status = document.querySelector("#import-status");
  const counts = document.querySelector("#import-counts");
  const outcomes = document.querySelector("#import-outcomes");
  const dismiss = document.querySelector("#import-dismiss");
  const retry = document.querySelector("#import-retry");
  const resolve = document.querySelector("#import-resolve");
  const resolveHelp = document.querySelector("#import-resolve-help");
  let locked = true;
  let timer = null;
  let currentRequest = null;
  let ownId = null;
  let pendingIds = [];
  let completedIds = [];
  let startPending = false;
  let hasActiveRun = false;
  let conflictPending = false;
  let notice = "";
  let storageUnavailable = false;
  let missingIds = [];

  try {
    const previousId = sessionStorage.getItem(LEGACY_RUN_KEY);
    if (previousId) {
      localStorage.setItem(RUN_KEY_PREFIX + previousId, "1");
      sessionStorage.removeItem(LEGACY_RUN_KEY);
    }
  } catch {
    storageUnavailable = true;
  }

  function readPendingRuns() {
    try {
      const ids = [];
      for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index);
        if (key?.startsWith(RUN_KEY_PREFIX)) ids.push(key.slice(RUN_KEY_PREFIX.length));
      }
      return ids.sort();
    } catch {
      storageUnavailable = true;
      return null;
    }
  }

  function rememberRun(id) {
    try {
      localStorage.setItem(RUN_KEY_PREFIX + id, "1");
      return true;
    } catch {
      storageUnavailable = true;
      return false;
    }
  }

  function forgetRun(id) {
    try {
      localStorage.removeItem(RUN_KEY_PREFIX + id);
      return true;
    } catch {
      storageUnavailable = true;
      return false;
    }
  }

  function lock(value) {
    locked = value;
    start.disabled = value;
    folder.disabled = value;
    setLocked(value);
  }

  function message(value) {
    status.textContent = notice ? `${notice} ${value}` : value;
  }

  function renderCounts(values) {
    counts.replaceChildren();
    if (!values) return;
    for (const [key, label] of COUNT_LABELS) {
      const item = document.createElement("li");
      item.textContent = `${label}: ${values[key]}`;
      counts.append(item);
    }
    if (values.unresolved_observations > 0) {
      const item = document.createElement("li");
      item.textContent = "Unresolved observations could not be confidently linked to a transaction.";
      counts.append(item);
    }
  }

  function poll() {
    clearTimeout(timer);
    timer = setTimeout(() => void refresh(), POLL_INTERVAL);
  }

  function showResolve(show) {
    resolve.hidden = !show;
    resolveHelp.hidden = !show;
  }

  function unavailable(storageUnavailable = false, canResolve = false) {
    lock(true);
    if (hasActiveRun || startPending || pendingIds.length) showImport();
    renderCounts(null);
    message(
      "Import status is unknown. " +
      (storageUnavailable ? "Storage or import ownership may be unavailable. " : "") +
      "Retry status; do not start another import.",
    );
    retry.hidden = false;
    showResolve(canResolve);
  }

  function storageError() {
    lock(true);
    showImport();
    renderCounts(null);
    message(STORAGE_NOTICE);
    retry.hidden = true;
    showResolve(false);
  }

  function outcome(run, own = false) {
    if (run.state === "succeeded") return own ? "Your import completed." : "Import completed.";
    if (run.state === "no_files") return "No eligible files were found.";
    if (run.state === "failed") return run.error?.message || "The import could not be completed.";
    return "Import outcome is unknown. Check transactions before retrying.";
  }

  function renderOutcomes(runs) {
    outcomes.replaceChildren();
    dismiss.hidden = pendingIds.length < 2 || completedIds.length === 0;
    if (pendingIds.length < 2) return;
    for (const run of runs) {
      if (!run || run.state === "running" || !completedIds.includes(run.id)) continue;
      const item = document.createElement("li");
      item.textContent = `${run.id}: ${outcome(run)}`;
      if (run.counts) {
        const details = document.createElement("ul");
        for (const [key, label] of COUNT_LABELS) {
          const count = document.createElement("li");
          count.textContent = `${label}: ${run.counts[key]}`;
          details.append(count);
        }
        if (run.counts.unresolved_observations > 0) {
          const explanation = document.createElement("li");
          explanation.textContent = "Unresolved observations could not be confidently linked to a transaction.";
          details.append(explanation);
        }
        item.append(details);
      }
      outcomes.append(item);
    }
  }

  function display(current, tracked) {
    if (storageUnavailable) {
      storageError();
      return;
    }
    if (conflictPending && !current) {
      unavailable();
      return;
    }
    conflictPending = false;
    const runs = pendingIds.map((id) => tracked.get(id));
    missingIds = pendingIds.filter((id) => !tracked.get(id));
    const unresolved = pendingIds.some((id, index) => {
      const run = runs[index];
      return !run || (id === ownId && startPending && run.state !== "running");
    });
    completedIds = pendingIds.filter((id, index) => {
      const run = runs[index];
      return run && run.state !== "running" && !(id === ownId && startPending);
    });
    renderOutcomes(runs);
    const ownRun = tracked.get(ownId) || runs.find((run) => run && run.state !== "running");
    if (unresolved) {
      if (current?.state === "running") {
        hasActiveRun = true;
        lock(true);
        showImport();
        renderCounts(null);
        message("Import status is unknown. Another import is running. Navigation is unavailable until it finishes. Retry status; do not start another import.");
        retry.hidden = false;
        showResolve(false);
        return;
      }
      unavailable(false, missingIds.length > 0);
      return;
    }
    retry.hidden = true;
    showResolve(false);
    renderCounts(pendingIds.length > 1 ? null : (ownRun || current)?.counts);
    if (current?.state === "running") {
      hasActiveRun = true;
      lock(true);
      showImport();
      const prefix = pendingIds.length > 1 ? "Import running." : ownRun && ownRun.id !== current.id ? `${outcome(ownRun, true)} Another import is running.` : "Import running.";
      message(`${prefix} Navigation is unavailable until it finishes.`);
      return;
    }
    if (runs.some((run) => run?.state === "running")) {
      unavailable();
      return;
    }
    if (!current && !ownRun) {
      hasActiveRun = false;
      lock(false);
      message("No import has been started.");
      return;
    }
    hasActiveRun = false;
    lock(false);
    const shown = ownRun || current;
    message(pendingIds.length > 1 ? "Recovered import outcomes are listed below." : outcome(shown, Boolean(ownRun && current && ownRun.id !== current.id)));
  }

  async function refresh(fresh = false) {
    if (currentRequest) {
      await currentRequest;
      if (fresh) return refresh();
      return;
    }
    clearTimeout(timer);
    currentRequest = (async () => {
      try {
        const ids = readPendingRuns();
        if (!ids) {
          storageError();
          return;
        }
        pendingIds = ids;
        const tracked = new Map();
        let current = null;
        if (ids.length) {
          for (const id of ids) {
            const data = await request("/api/imports/status", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ id }),
            });
            if (!data || !validRun(data.run) || !validRun(data.current) || (data.run && data.run.id !== id)) {
              unavailable();
              return;
            }
            tracked.set(id, data.run);
            current = data.current;
          }
        } else {
          const data = await request("/api/imports/current");
          if (!data || !validRun(data.run)) {
            unavailable();
            return;
          }
          current = data.run;
        }
        const latestIds = readPendingRuns();
        if (!latestIds) {
          storageError();
        } else if (ids.join(",") !== latestIds.join(",")) {
          pendingIds = latestIds;
          unavailable();
        } else {
          display(current, tracked);
        }
      } catch (error) {
        unavailable(error instanceof HttpError && error.status === 503);
      }
    })();
    try {
      await currentRequest;
    } finally {
      currentRequest = null;
      poll();
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (locked) return;
    notice = "";
    const storedIds = readPendingRuns();
    if (!storedIds) {
      storageError();
      return;
    }
    if (storedIds.some((id) => !completedIds.includes(id))) {
      pendingIds = storedIds;
      unavailable();
      void refresh(true);
      return;
    }
    if (storedIds.length <= 1) {
      for (const id of completedIds) {
        if (!forgetRun(id)) {
          storageError();
          return;
        }
      }
    }
    completedIds = [];
    const requestId = crypto.randomUUID();
    if (!rememberRun(requestId)) {
      storageError();
      return;
    }
    ownId = requestId;
    pendingIds = storedIds.length > 1 ? [...storedIds, requestId] : [requestId];
    startPending = true;
    hasActiveRun = true;
    lock(true);
    renderCounts(null);
    retry.hidden = true;
    message("Starting import...");
    try {
      const result = await request("/api/imports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input_dir: folder.value, request_id: requestId }),
      });
      if (ownId !== requestId || !startPending) return;
      startPending = false;
      if (!result || result.id !== requestId || result.state !== "running") {
        unavailable();
        await refresh(true);
        return;
      }
      await refresh(true);
    } catch (error) {
      if (ownId !== requestId || !startPending) return;
      startPending = false;
      if (error instanceof HttpError && error.status === 422) {
        if (!forgetRun(requestId)) {
          storageError();
          return;
        }
        ownId = null;
        hasActiveRun = false;
        notice = INPUT_NOTICE;
        message("Your import was not started.");
        await refresh(true);
      } else if (error instanceof HttpError && error.code === "import_request_closed") {
        await refresh(true);
      } else if (error instanceof HttpError && error.status === 409) {
        if (!forgetRun(requestId)) {
          storageError();
          return;
        }
        ownId = null;
        conflictPending = true;
        notice = "Your import was not started because another import is running.";
        unavailable();
        await refresh(true);
      } else if (error instanceof HttpError && error.code === "import_not_started") {
        if (!forgetRun(requestId)) {
          storageError();
          return;
        }
        ownId = null;
        hasActiveRun = false;
        notice = "Your import was not started. Storage or import ownership is unavailable.";
        await refresh(true);
      } else {
        unavailable();
        await refresh(true);
      }
    }
  });

  retry.addEventListener("click", () => void refresh());
  resolve.addEventListener("click", async () => {
    resolve.disabled = true;
    notice = "";
    try {
      for (const id of missingIds) {
        const result = await request("/api/imports/resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        if (!result || result.id !== id) {
          unavailable();
          return;
        }
        if (id === ownId) startPending = false;
      }
    } catch (error) {
      notice = error instanceof HttpError && error.status === 409
        ? "The unrecorded import could not be resolved while another import is running."
        : "The unrecorded import could not be resolved. Retry status before trying again.";
      unavailable(error instanceof HttpError && error.status === 503);
    } finally {
      resolve.disabled = false;
      await refresh(true);
    }
  });
  dismiss.addEventListener("click", () => {
    for (const id of completedIds) {
      if (!forgetRun(id)) {
        storageError();
        return;
      }
    }
    completedIds = [];
    void refresh(true);
  });
  window.addEventListener("storage", (event) => {
    if (event.key?.startsWith(RUN_KEY_PREFIX)) void refresh(true);
  });
  lock(true);
  return { refresh };
}
