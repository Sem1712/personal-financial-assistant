function amount(cents, currency) {
  const negative = cents.startsWith("-");
  const digits = (negative ? cents.slice(1) : cents).padStart(3, "0");
  return `${negative ? "-" : ""}${digits.slice(0, -2)}.${digits.slice(-2)} ${currency}`;
}

function parseAmount(value) {
  if (!/^[+]?(?:[0-9]+(?:\.[0-9]{0,2})?|\.[0-9]{1,2})$/.test(value)) {
    throw new Error("Enter a nonnegative EUR amount with at most two decimal places.");
  }
  const [whole, fraction = ""] = value.replace(/^[+]/, "").split(".");
  const significant = (whole || "0").replace(/^0+/, "") || "0";
  if (significant.length > 17) throw new Error("EUR amount is out of range.");
  const cents = BigInt(significant) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (cents > 2n ** 63n) {
    throw new Error("EUR amount is out of range.");
  }
  return cents;
}

class FilterValidationError extends Error {
  constructor(message, fields) {
    super(message);
    this.fields = fields;
  }
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
  const pageControls = [...document.querySelectorAll("[data-page-action]")];
  const topPagination = document.querySelector("#transaction-pages-top");
  const summary = document.querySelector("#filters-summary");
  const filterError = document.querySelector("#filter-error");
  const detailHeading = document.querySelector("#detail-heading");
  const detailContext = document.querySelector("#detail-context");
  const detailRecordStatus = document.querySelector("#detail-record-status");
  const detailStatus = document.querySelector("#detail-status");
  const observations = document.querySelector("#detail-observations");
  const detailRetry = document.querySelector("#detail-retry");
  let filters = {};
  let currentCursor = null;
  let previousCursors = [];
  let nextCursor = null;
  let generation = 0;
  let detailGeneration = 0;
  let validationError = null;
  let categoryGeneration = 0;
  let selectedItem = null;
  let initiatingControl = null;

  function setStatus(element, text, kind) {
    element.dataset.kind = kind;
    if (element.textContent !== text) element.textContent = text;
  }

  function renderPagination(loading = false) {
    for (const control of pageControls) {
      control.disabled = loading || (control.dataset.pageAction === "next" ? !nextCursor : previousCursors.length === 0);
      control.parentElement.classList.toggle("disabled", control.disabled);
    }
  }

  function setListLoading(loading) {
    list.inert = loading;
    list.setAttribute("aria-busy", String(loading));
  }

  function finishLoadingFocus(control, target, fallback = target) {
    if (!control || document.activeElement !== target || target.closest("[hidden]")) return;
    const destination = control.isConnected && !control.hidden && !control.disabled ? control : fallback;
    if (destination !== target) destination.focus();
  }

  function clearValidation() {
    for (const input of form.querySelectorAll("[aria-invalid]")) {
      input.removeAttribute("aria-invalid");
      if (input.id === "amount-min" || input.id === "amount-max") {
        input.setAttribute("aria-describedby", "amount-help");
      } else {
        input.removeAttribute("aria-describedby");
      }
      input.classList.remove("is-invalid");
    }
    filterError.textContent = "";
  }

  function renderSummary() {
    const labels = { date_from: "From date", date_to: "To date", booking_status: "Booking status", text: "Description", amount_min: "Minimum absolute amount (EUR)", amount_max: "Maximum absolute amount (EUR)" };
    const parts = [];
    for (const [key, label] of Object.entries(labels)) {
      if (filters[key]) parts.push(`${label}: ${filters[key]}`);
    }
    if (filters.category) {
      parts.push(`Bank-suggested category: ${filters.category.kind === "value" ? filters.category.value : "No recorded category"}`);
    }
    if (filters.direction) {
      parts.push(`Transaction type: ${filters.direction === "withdrawals" ? "Withdrawals" : "Deposits"}`);
    }
    summary.textContent = parts.length ? `Applied filters: ${parts.join("; ")}` : "All recorded transactions";
  }

  function readAmount(id) {
    const value = document.getElementById(id).value.trim();
    try {
      return value ? parseAmount(value) : null;
    } catch (error) {
      if (!(error instanceof Error)) throw error;
      throw new FilterValidationError(error.message, [id]);
    }
  }

  function readFilters() {
    const fromInput = document.querySelector("#date-from");
    const toInput = document.querySelector("#date-to");
    if (fromInput.validity.badInput || toInput.validity.badInput) {
      throw new FilterValidationError("Enter a valid date or leave the date field empty.", [fromInput, toInput].filter((input) => input.validity.badInput).map((input) => input.id));
    }
    const from = fromInput.value;
    const to = toInput.value;
    const unsupportedDates = [fromInput, toInput].filter(
      (input) => input.value && !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(input.value),
    );
    if (unsupportedDates.length) {
      throw new FilterValidationError("Enter a date between 0001-01-01 and 9999-12-31.", unsupportedDates.map((input) => input.id));
    }
    const min = document.querySelector("#amount-min").value.trim();
    const max = document.querySelector("#amount-max").value.trim();
    if (from && to && from > to) throw new FilterValidationError("End date must not precede start date.", ["date-from", "date-to"]);
    const minCents = readAmount("amount-min");
    const maxCents = readAmount("amount-max");
    if (minCents !== null && maxCents !== null && minCents > maxCents) {
      throw new FilterValidationError("Maximum amount must not be less than minimum amount.", ["amount-min", "amount-max"]);
    }
    const result = {};
    if (from) result.date_from = from;
    if (to) result.date_to = to;
    const booking = document.querySelector("#booking-status").value;
    const text = document.querySelector("#description").value;
    if (booking) result.booking_status = booking;
    const direction = document.querySelector("#transaction-direction").value;
    if (direction) result.direction = direction;
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
    const sequence = ++categoryGeneration;
    const focusedRetry = document.activeElement === categoryRetry ? categoryRetry : null;
    setStatus(categoryStatus, "Loading bank-suggested categories...", "loading");
    if (focusedRetry) categoryStatus.focus();
    categoryRetry.hidden = true;
    try {
      const data = await post("/api/transactions/categories", {});
      if (sequence !== categoryGeneration) return;
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
      setStatus(categoryStatus, "", "available");
      categoryRetry.hidden = true;
    } catch {
      if (sequence !== categoryGeneration) return;
      setStatus(categoryStatus, "Could not retrieve bank-suggested categories.", "failed");
      categoryRetry.hidden = false;
    } finally {
      if (sequence === categoryGeneration) finishLoadingFocus(focusedRetry, categoryStatus, category);
    }
  }

  function addText(parent, tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    parent.append(element);
    return element;
  }

  function clearDetails(returnFocus = false) {
    ++detailGeneration;
    selectedItem = null;
    details.hidden = true;
    list.after(details);
    observations.replaceChildren();
    detailContext.textContent = "";
    detailRecordStatus.textContent = "";
    initiatingControl?.setAttribute("aria-expanded", "false");
    if (returnFocus && initiatingControl?.isConnected && !initiatingControl.closest("[hidden]")) {
      initiatingControl.focus();
    }
    initiatingControl = null;
  }

  async function loadDetails() {
    const item = selectedItem;
    if (!item) return;
    const sequence = ++detailGeneration;
    observations.replaceChildren();
    setStatus(detailStatus, "Loading transaction details...", "loading");
    detailRetry.hidden = true;
    try {
      const data = await post("/api/transactions/detail", { id: item.id });
      if (sequence !== detailGeneration) return;
      if (data.id !== item.id || !Array.isArray(data.observations)) throw new Error("Invalid transaction details response");
      setStatus(detailStatus, "", "ready");
      addText(observations, "h4", "Source observations").className = "h6";
      if (!data.observations.length) addText(observations, "p", "No linked source observations are available.");
      for (const observation of data.observations) {
        const source = document.createElement("div");
        source.className = "source-observation";
        addText(source, "p", `Operation: ${observation.operation ?? "Unavailable"}`);
        addText(source, "p", `Details: ${observation.details ?? "Unavailable"}`);
        addText(source, "p", `Bank suggestion: ${observation.category ?? "Unavailable"}`);
        addText(source, "p", `Source booking status: ${observation.booking_status}`);
        observations.append(source);
      }
    } catch {
      if (sequence !== detailGeneration) return;
      observations.replaceChildren();
      setStatus(detailStatus, "Could not retrieve transaction details. Try again.", "failed");
      detailRetry.hidden = false;
    }
  }

  function showDetails(item, button) {
    if (selectedItem?.id === item.id) {
      clearDetails(true);
      return;
    }
    clearDetails();
    selectedItem = item;
    initiatingControl = button;
    button.setAttribute("aria-expanded", "true");
    button.closest(".transaction-row").append(details);
    details.hidden = false;
    detailContext.textContent = `${item.date} | ${amount(item.amount_minor, item.currency)} | Record ${item.id}`;
    detailRecordStatus.textContent = `Booking status: ${item.booking_status}; reconciliation: ${item.reconciliation_state}${item.ongoing_expense ? "; ongoing expense" : ""}`;
    void loadDetails();
  }

  async function load(pageControl = null) {
    const sequence = ++generation;
    const pageAction = pageControl?.dataset.pageAction ?? null;
    const fromBottom = pageControl !== null && !topPagination.contains(pageControl);
    const paginationBounds = topPagination.getBoundingClientRect();
    const scrollPosition = pageAction === null ? null : {
      left: window.scrollX,
      top: window.scrollY,
      keepPosition: !fromBottom && paginationBounds.top >= 0 && paginationBounds.bottom <= window.innerHeight,
    };
    const focusedControl = [...pageControls, retry].find((control) => document.activeElement === control);
    clearDetails();
    renderSummary();
    setStatus(status, "Loading transactions...", "loading");
    if (focusedControl) status.focus({ preventScroll: pageAction !== null });
    if (pageAction === null) list.replaceChildren();
    setListLoading(true);
    retry.hidden = true;
    importButton.hidden = true;
    nextCursor = null;
    renderPagination(true);
    try {
      const data = await post("/api/transactions/search", {
        ...filters,
        ...(currentCursor ? { cursor: currentCursor } : {}),
      });
      if (sequence !== generation) return;
      if (!Array.isArray(data.items) || typeof data.history_exists !== "boolean" ||
          data.items.some((item) => !Array.isArray(item.operations) || item.operations.some((operation) => typeof operation !== "string") ||
            !Array.isArray(item.details) || item.details.some((text) => typeof text !== "string"))) {
        throw new Error("Invalid transaction response");
      }
      nextCursor = data.next_cursor;
      if (!data.history_exists) {
        setStatus(status, "No recorded transactions. Import exports to get started.", "empty-history");
        importButton.hidden = false;
      } else if (!data.items.length) {
        setStatus(status, "No transactions match these filters. Clear filters to see all records.", "no-matches");
      } else {
        setStatus(status, `${data.items.length} transactions on this page.`, "populated");
      }
      const rows = document.createDocumentFragment();
      for (const item of data.items) {
        const row = document.createElement("article");
        row.className = "transaction-row";
        row.dataset.occurrenceId = item.id;
        const signedAmount = BigInt(item.amount_minor);
        row.dataset.direction = signedAmount > 0n ? "positive" : signedAmount < 0n ? "negative" : "neutral";
        if (signedAmount > 0n && filters.direction !== "deposits") {
          row.dataset.highlight = "positive";
        } else if (item.currency === "EUR" && signedAmount <= -9995n) {
          row.dataset.highlight = "large-expense";
        }
        for (const [label, value, className] of [
          ["Operation", item.operations.length ? item.operations.join("\n") : "Operation unavailable", "transaction-operation"],
          ["Date", item.date, ""],
          ["Signed amount", amount(item.amount_minor, item.currency), "transaction-amount"],
        ]) {
          const cell = document.createElement("div");
          addText(cell, "span", label).className = "cell-label";
          addText(cell, "p", value).className = `mb-0 ${className}`;
          if (className === "transaction-operation") {
            addText(cell, "p", item.details.length ? item.details.join("; ") : "Details unavailable").className = "transaction-source-details mb-0";
          }
          row.append(cell);
        }
        const button = addText(row, "button", "Details");
        button.className = "btn transaction-toggle";
        button.type = "button";
        button.setAttribute("aria-controls", "transaction-details");
        button.setAttribute("aria-expanded", "false");
        button.addEventListener("click", () => showDetails(item, button));
        rows.append(row);
      }
      list.replaceChildren(rows);
    } catch {
      if (sequence !== generation) return;
      list.replaceChildren();
      setStatus(status, "Could not retrieve transactions. Retry when storage is available.", "failed");
      retry.hidden = false;
    } finally {
      if (sequence === generation) {
        setListLoading(false);
        renderPagination();
        if (pageAction !== null && focusedControl) {
          if (document.activeElement === status && !status.closest("[hidden]")) {
            const top = scrollPosition.keepPosition ? scrollPosition.top :
              window.scrollY + topPagination.getBoundingClientRect().top - 12;
            const behavior = fromBottom && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "instant";
            window.scrollTo({ left: scrollPosition.left, top: Math.max(0, top), behavior });
            const topControl = topPagination.querySelector(`[data-page-action="${pageAction}"]`);
            (topControl.disabled ? status : topControl).focus({ preventScroll: true });
          }
        } else {
          finishLoadingFocus(focusedControl, status);
        }
      }
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    clearValidation();
    try {
      filters = readFilters();
    } catch (error) {
      if (!(error instanceof FilterValidationError)) throw error;
      validationError = error.message;
      filterError.textContent = validationError;
      for (const id of error.fields) {
        const input = document.getElementById(id);
        input.setAttribute("aria-invalid", "true");
        input.setAttribute("aria-describedby", "filter-error");
        input.classList.add("is-invalid");
      }
      ++generation;
      clearDetails();
      list.replaceChildren();
      setListLoading(false);
      retry.hidden = true;
      importButton.hidden = true;
      renderPagination(true);
      setStatus(status, "Filters need correction. Update the highlighted fields and apply again.", "invalid-input");
      return;
    }
    validationError = null;
    currentCursor = null;
    previousCursors = [];
    void load();
  });
  document.querySelector("#clear-filters").addEventListener("click", () => {
    form.reset();
    clearValidation();
    filters = {};
    validationError = null;
    currentCursor = null;
    previousCursors = [];
    void load();
  });
  for (const control of pageControls) {
    control.addEventListener("click", () => {
      const action = control.dataset.pageAction;
      if (action === "next") {
        if (!nextCursor) return;
        previousCursors.push(currentCursor);
        currentCursor = nextCursor;
      } else if (action === "previous") {
        if (!previousCursors.length) return;
        currentCursor = previousCursors.pop();
      } else {
        if (!previousCursors.length) return;
        currentCursor = null;
        previousCursors = [];
      }
      void load(control);
    });
  }
  retry.addEventListener("click", () => void load());
  categoryRetry.addEventListener("click", () => void loadCategories());
  detailRetry.addEventListener("click", () => {
    detailHeading.focus();
    void loadDetails();
  });
  return {
    leave() {
      ++generation;
      ++categoryGeneration;
      clearDetails();
      setListLoading(false);
    },
    refresh() {
      currentCursor = null;
      previousCursors = [];
      void loadCategories();
      if (validationError !== null) {
        setStatus(status, "Filters need correction. Update the highlighted fields and apply again.", "invalid-input");
        return;
      }
      return load();
    },
  };
}
