const ALLOW_URL = "http://localhost:9001/allow";

document.addEventListener("DOMContentLoaded", () => {
  try {
    chrome.storage.local.get(
      ["blockedTabUrl", "blockedTabTitle", "blockReason"],
      ({ blockedTabUrl, blockedTabTitle, blockReason }) => {
        try {
          const urlText = blockedTabUrl || blockedTabTitle || "";
          const reasonText = blockReason || "";

          const blockedUrlElement = document.getElementById("blockedUrl");
          const blockReasonElement = document.getElementById("blockReason");
          const allowButton = document.getElementById("allowButton");
          const closeButton = document.getElementById("closeButton");

          if (blockedUrlElement) blockedUrlElement.textContent = urlText;
          if (blockReasonElement) blockReasonElement.textContent = reasonText;

          if (allowButton) {
            allowButton.addEventListener("click", () => {
              fetch(ALLOW_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ type: "allow", url: blockedTabUrl || "" }),
              })
                .catch(() => {})
                .finally(() => {
                  try {
                    window.history.back();
                  } catch (error) {}
                });
            });
          }

          if (closeButton) {
            closeButton.addEventListener("click", () => {
              chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                try {
                  if (!tabs || !tabs[0]) return;
                  chrome.tabs.remove(tabs[0].id);
                } catch (error) {}
              });
            });
          }
        } catch (error) {}
      }
    );
  } catch (error) {}
});
