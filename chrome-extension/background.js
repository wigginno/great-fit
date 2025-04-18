// A global promise to avoid race conditions creating the offscreen document
let creating;

// Function to get the existing offscreen document or create a new one
async function setupOffscreenDocument(path) {
  // Check if we already have an offscreen document.
  if (await chrome.offscreen.hasDocument?.()) {
    console.log("Offscreen document already exists.");
    return;
  }

  // Avoid race conditions - create only one instance
  if (creating) {
    await creating;
  } else {
    creating = chrome.offscreen.createDocument({
      url: path,
      reasons: [chrome.offscreen.Reason.CLIPBOARD],
      justification: "Needed to copy generated Markdown to the clipboard",
    });
    await creating;
    creating = null; // Reset the promise
    console.log("Offscreen document created.");
  }
}

chrome.action.onClicked.addListener(async (tab) => {
  // Ensure the tab has a valid ID
  if (!tab.id) {
    console.error("Could not get active tab ID.");
    return;
  }

  console.log(`Action clicked on tab: ${tab.id}`);

  try {
    console.log("Injecting content script into tab:", tab.id);
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: [
        "https://cdn.jsdelivr.net/npm/turndown@7.1.3/dist/turndown.min.js",
        "content-converter.js",
      ],
    });

    if (chrome.runtime.lastError) {
      console.error(
        "Script injection failed:",
        chrome.runtime.lastError.message,
      );
      return;
    }

    if (results && results.length > 0 && results[0].result) {
      const markdownContent = results[0].result;
      console.log("Markdown received from content script.");
      // Log the beginning of the received content
      console.log(
        "Received content (start):",
        typeof markdownContent === "string"
          ? markdownContent.substring(0, 500) + "..."
          : "[Not a string]",
      );

      if (markdownContent.startsWith("Error:")) {
        console.error("Content script reported an error:", markdownContent);
        // Handle error - maybe show a notification
        return;
      }

      // Setup and send to offscreen document
      await setupOffscreenDocument("offscreen.html");

      console.log("Sending markdown to offscreen document for copying...");
      const response = await chrome.runtime.sendMessage({
        type: "copy-to-clipboard",
        target: "offscreen-doc",
        data: markdownContent,
      });

      console.log("Message sent, response:", response);
      // Optional: Close the offscreen document after a short delay
      // This gives the clipboard time to process. Adjust as needed.
      // setTimeout(async () => {
      //   if (await chrome.offscreen.hasDocument?.()) {
      //      await chrome.offscreen.closeDocument();
      //      console.log("Offscreen document closed.");
      //   }
      // }, 2000);

      // Add user feedback here (e.g., notification)
      /*
      chrome.notifications.create({
        type: 'basic',
        title: 'HTML to Markdown',
        message: 'Markdown copied to clipboard!',
        priority: 0
      });
      */
    } else {
      console.warn(
        "Script injection succeeded, but no markdown result returned.",
      );
      // Handle case where no result is returned
    }
  } catch (err) {
    console.error(`Failed to execute script or handle result: ${err}`, err);
    // Add user feedback for failure
  }
});

// Optional: Listen for messages back from offscreen if needed (e.g., confirmation)
// chrome.runtime.onMessage.addListener((message) => {
//   if (message.type === 'copy-success') {
//     console.log('Background script received copy success confirmation.');
//   } else if (message.type === 'copy-failure') {
//     console.error('Background script received copy failure:', message.error);
//   }
// });

console.log("Background service worker started and listener added.");

// Add permission requirement for notifications
// Need to add "notifications" to manifest.json permissions array!
