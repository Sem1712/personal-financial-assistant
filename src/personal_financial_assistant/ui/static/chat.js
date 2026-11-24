export function createChatView(showView) {
  document.querySelector("#chat-import").addEventListener("click", () => showView("import"));
  document.querySelector("#chat-transactions").addEventListener("click", () => showView("transactions"));
}
