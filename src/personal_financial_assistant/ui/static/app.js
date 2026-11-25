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
const viewRoots = ["chat", "import", "transactions"].map((id) => document.getElementById(id));
let visibleView = "chat";

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
  const changed = visibleView !== name;
  if (changed) {
    navigationStatus.textContent = "";
    if (visibleView === "transactions") transactions.leave();
  }
  for (const section of viewRoots) {
    section.hidden = section.id !== name;
  }
  for (const button of document.querySelectorAll(".app-navigation [data-view]")) {
    if (button.dataset.view === name) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  visibleView = name;
  if (changed) document.querySelector(`#${name} h2`).focus();
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
