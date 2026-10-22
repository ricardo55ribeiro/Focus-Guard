const SERVER_URL = "http://localhost:9001";

function shouldSkipUrl(url) {
  return (
    !url ||
    url.startsWith("chrome://") ||
    url.startsWith("about:") ||
    url.startsWith("chrome-extension://") ||
    url.startsWith("moz-extension://") ||
    url.includes("blocking.html")
  );
}

function sendTabData(tab) {
  if (!tab || shouldSkipUrl(tab.url)) return;

  fetch(SERVER_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: tab.url || "", title: tab.title || "" }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.action === "block") {
        redirectActiveTab(data.reason);
      }
    })
    .catch(() => {});
}

function redirectActiveTab(reason) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || !tabs[0]) return;
    const tab = tabs[0];
    if (
      !tab.url ||
      tab.url.startsWith("chrome://") ||
      tab.url.startsWith("about:") ||
      tab.url.includes("blocking.html")
    ) {
      return;
    }

    chrome.storage.local.set(
      {
        blockedTabUrl: tab.url,
        blockedTabTitle: tab.title,
        blockReason: reason,
      },
      () => {
        chrome.tabs.update(tab.id, { url: chrome.runtime.getURL("blocking.html") });
      }
    );
  });
}

function sendActiveTab() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (chrome.runtime.lastError) return;
    const [tab] = tabs || [];
    sendTabData(tab);
  });
}

chrome.tabs.onActivated.addListener(() => sendActiveTab());
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete") sendActiveTab();
});

chrome.runtime.onInstalled.addListener(() => sendActiveTab());
sendActiveTab();
