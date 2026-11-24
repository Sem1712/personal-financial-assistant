import { createImportView } from "./import.js";
import { createChatView } from "./chat.js";
import { createTransactionView } from "./transactions.js";

const token = document.querySelector('meta[name="pfa-token"]').content;

export class HttpError extends Error {
  constructor(status, message, code = null) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 75000);
  try {
    const response = await fetch(path, {
      ...options,
      headers: { "X-PFA-Token": token, ...options.headers },
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) {
      throw new HttpError(response.status, result.error?.message || "Request failed.", result.error?.code);
    }
    return result;
  } finally {
    clearTimeout(timer);
  }
}

let navigationLocked = true;
let navigationSequence = 0;
const navigationStatus = document.querySelector("#navigation-status");

export function showView(name, force = false) {
  const sequence = ++navigationSequence;
  if (navigationLocked && name !== "import" && !force) {
    navigationStatus.textContent = "Navigation is unavailable while an import may be running.";
    return;
  }
  if (name === "import" || force) {
    renderView(name);
    return;
  }
  void (async () => {
    await imports.refresh(true);
    if (sequence !== navigationSequence) return;
    if (navigationLocked) {
      navigationStatus.textContent = "Navigation is unavailable while an import may be running.";
      return;
    }
    renderView(name);
  })();
}

function renderView(name) {
  navigationStatus.textContent = "";
  for (const section of document.querySelectorAll("main section")) {
    section.hidden = section.id !== name;
  }
  if (name === "transactions") void transactions.refresh();
}

for (const button of document.querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => showView(button.dataset.view));
}

const imports = createImportView({
  request,
  HttpError,
  setLocked(value) {
    navigationLocked = value;
    if (!value) {
      navigationStatus.textContent = "";
    } else if (!navigationStatus.textContent) {
      navigationStatus.textContent = "Import status must be checked before navigating.";
    }
  },
  showImport() {
    showView("import", true);
  },
});
const transactions = createTransactionView({ request });
createChatView(showView);
void imports.refresh();
