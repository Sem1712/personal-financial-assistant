function amount(cents, currency) {
  const negative = cents.startsWith("-");
  const digits = (negative ? cents.slice(1) : cents).padStart(3, "0");
  return `${negative ? "-" : ""}${digits.slice(0, -2)}.${digits.slice(-2)} ${currency}`;
}

function parseAmount(value) {
  if (!/^[+-]?(?:[0-9]+(?:\.[0-9]{0,2})?|\.[0-9]{1,2})$/.test(value)) {
    throw new Error("Enter a signed EUR amount with at most two decimal places.");
  }
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = value.replace(/^[+-]/, "").split(".");
  const significant = (whole || "0").replace(/^0+/, "") || "0";
  if (significant.length > 17) throw new Error("EUR amount is out of range.");
  const cents = BigInt(significant) * 100n + BigInt(fraction.padEnd(2, "0"));
  const signed = negative ? -cents : cents;
  if (signed < -(2n ** 63n) || signed >= 2n ** 63n) {
    throw new Error("EUR amount is out of range.");
  }
  return signed;
}

export function createTransactionView({ request }) {
  const form = document.querySelector("#transaction-filters");
  const status = document.querySelector("#transaction-status");
  const list = document.querySelector("#transaction-list");
  const details = document.querySelector("#transaction-details");
  const retry = document.querySelector("#transaction-retry");
  const importButton = document.querySelector("#transaction-import");
  const category = document.querySelector("#category");
  const categoryStatus = document.querySelector("#category-status");
  const categoryRetry = document.querySelector("#category-retry");
  const previous = document.querySelector("#previous-page");
  const next = document.querySelector("#next-page");
  let filters = {};
  let currentCursor = null;
  let previousCursors = [];
  let nextCursor = null;
  let generation = 0;
  let detailGeneration = 0;
  let validationError = null;

  function readFilters() {
    const fromInput = document.querySelector("#date-from");
    const toInput = document.querySelector("#date-to");
    if (fromInput.validity.badInput || toInput.validity.badInput) {
      throw new Error("Enter a valid date or leave the date field empty.");
    }
    const from = fromInput.value;
    const to = toInput.value;
    const min = document.querySelector("#amount-min").value.trim();
    const max = document.querySelector("#amount-max").value.trim();
    if (from && to && from > to) throw new Error("End date must not precede start date.");
    const minCents = min ? parseAmount(min) : null;
    const maxCents = max ? parseAmount(max) : null;
    if (minCents !== null && maxCents !== null && minCents > maxCents) {
      throw new Error("Maximum amount must not be less than minimum amount.");
    }
    const result = {};
    if (from) result.date_from = from;
    if (to) result.date_to = to;
    const booking = document.querySelector("#booking-status").value;
    const text = document.querySelector("#description").value;
    if (booking) result.booking_status = booking;
    if (text) result.text = text;
    if (category.value === "none") result.category = { kind: "no_recorded_category" };
    else if (category.value.startsWith("value:")) {
      result.category = { kind: "value", value: category.value.slice(6) };
    }
    if (min) result.amount_min = min;
    if (max) result.amount_max = max;
    return result;
  }

  async function post(path, body) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function loadCategories() {
    try {
      const data = await post("/api/transactions/categories", {});
      if (!Array.isArray(data.categories) || data.categories.some((value) => typeof value !== "string")) {
        throw new Error("Invalid categories response");
      }
      const selected = category.value;
      category.replaceChildren(new Option("All categories", ""), new Option("No recorded category", "none"));
      for (const value of data.categories) category.add(new Option(value, `value:${value}`));
      if (selected.startsWith("value:") && !data.categories.includes(selected.slice(6))) {
        category.add(new Option(selected.slice(6), selected));
      }
      category.value = selected;
      if (category.selectedIndex < 0) category.value = "";
      categoryStatus.textContent = "";
      categoryRetry.hidden = true;
    } catch {
      categoryStatus.textContent = "Could not retrieve bank-suggested categories.";
      categoryRetry.hidden = false;
    }
  }

  function addText(parent, tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    parent.append(element);
    return element;
  }

  async function showDetails(id) {
    const sequence = ++detailGeneration;
    details.replaceChildren();
    addText(details, "p", "Loading transaction details...");
    try {
      const data = await post("/api/transactions/detail", { id });
      if (sequence !== detailGeneration) return;
      details.replaceChildren();
      addText(details, "h3", "Source observations");
      if (!data.observations.length) addText(details, "p", "No linked source observations are available.");
      for (const observation of data.observations) {
        const source = document.createElement("div");
        addText(source, "p", `Operation: ${observation.operation ?? "Unavailable"}`);
        addText(source, "p", `Details: ${observation.details ?? "Unavailable"}`);
        addText(source, "p", `Bank suggestion: ${observation.category ?? "Unavailable"}`);
        addText(source, "p", `Source booking status: ${observation.booking_status}`);
        details.append(source);
      }
    } catch {
      if (sequence === detailGeneration) details.textContent = "Could not retrieve transaction details. Try again.";
    }
  }

  async function load() {
    const sequence = ++generation;
    ++detailGeneration;
    status.textContent = "Loading transactions...";
    list.replaceChildren();
    details.replaceChildren();
    retry.hidden = true;
    importButton.hidden = true;
    next.hidden = true;
    previous.hidden = true;
    try {
      const data = await post("/api/transactions/search", {
        ...filters,
        ...(currentCursor ? { cursor: currentCursor } : {}),
      });
      if (sequence !== generation) return;
      if (!Array.isArray(data.items) || typeof data.history_exists !== "boolean") {
        throw new Error("Invalid transaction response");
      }
      nextCursor = data.next_cursor;
      if (!data.history_exists) {
        status.textContent = "No recorded transactions. Import exports to get started.";
        importButton.hidden = false;
      } else if (!data.items.length) {
        status.textContent = "No transactions match these filters. Clear filters to see all records.";
      } else {
        status.textContent = `${data.items.length} transactions on this page.`;
      }
      for (const item of data.items) {
        const row = document.createElement("article");
        addText(row, "p", item.date);
        addText(row, "p", amount(item.amount_minor, item.currency));
        addText(row, "p", `Booking status: ${item.booking_status}; reconciliation: ${item.reconciliation_state}${item.ongoing_expense ? "; ongoing expense" : ""}`);
        const button = addText(row, "button", "View details");
        button.type = "button";
        button.addEventListener("click", () => void showDetails(item.id));
        list.append(row);
      }
      previous.hidden = previousCursors.length === 0;
      next.hidden = !nextCursor;
    } catch {
      if (sequence !== generation) return;
      status.textContent = "Could not retrieve transactions. Retry when storage is available.";
      retry.hidden = false;
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      filters = readFilters();
    } catch (error) {
      validationError = error.message;
      ++generation;
      ++detailGeneration;
      list.replaceChildren();
      details.replaceChildren();
      retry.hidden = true;
      importButton.hidden = true;
      previous.hidden = true;
      next.hidden = true;
      status.textContent = validationError;
      return;
    }
    validationError = null;
    currentCursor = null;
    previousCursors = [];
    void load();
  });
  document.querySelector("#clear-filters").addEventListener("click", () => {
    form.reset();
    filters = {};
    validationError = null;
    currentCursor = null;
    previousCursors = [];
    void load();
  });
  next.addEventListener("click", () => {
    if (!nextCursor) return;
    previousCursors.push(currentCursor);
    currentCursor = nextCursor;
    void load();
  });
  previous.addEventListener("click", () => {
    if (!previousCursors.length) return;
    currentCursor = previousCursors.pop();
    void load();
  });
  retry.addEventListener("click", () => void load());
  categoryRetry.addEventListener("click", () => void loadCategories());
  return {
    refresh() {
      currentCursor = null;
      previousCursors = [];
      void loadCategories();
      if (validationError !== null) {
        status.textContent = validationError;
        return;
      }
      return load();
    },
  };
}
