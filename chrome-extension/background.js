// A global promise to avoid race conditions creating the offscreen document

chrome.action.onClicked.addListener(async (tab) => {
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: [
      "turndown.min.js",
      "content-converter.js",
    ],
  });

  const markdownContent = results[0].result;
  // Use the main API endpoint for submitting job markdown
  const apiUrl = "http://localhost:8000/jobs/markdown";

  fetch(apiUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // Add any other headers like Authorization if needed in the future
    },
    body: JSON.stringify({ content: markdownContent }),
  });
});
