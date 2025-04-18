// A global promise to avoid race conditions creating the offscreen document
// Removed offscreen document logic

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
        "turndown.min.js", // Load local file
        "content-converter.js",
      ],
    });

    if (chrome.runtime.lastError) {
      console.error(
        "Script injection failed:",
        chrome.runtime.lastError.message,
      );
      // Show user feedback for injection failure
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon48.png', // Optional: add an icon
        title: 'Great Fit Saver',
        message: 'Error: Could not inject script into the page.',
        priority: 1
      });
      return;
    }

    if (results && results.length > 0 && results[0].result) {
      const markdownContent = results[0].result;
      console.log("Markdown received from content script.");
      console.log(
        "Received content (start):",
        typeof markdownContent === "string"
          ? markdownContent.substring(0, 500) + "..."
          : "[Not a string]",
      );

      if (typeof markdownContent !== 'string' || markdownContent.startsWith("Error:")) {
        console.error("Content script reported an error or returned invalid data:", markdownContent);
        chrome.notifications.create({
            type: 'basic',
            iconUrl: 'icons/icon48.png',
            title: 'Great Fit Saver',
            message: 'Error: Could not extract job content from the page.',
            priority: 1
        });
        return;
      }

      // ---- START API Call ----
      const userId = 1; // Hardcoded user ID for now
      const apiUrl = `http://127.0.0.1:8000/users/${userId}/jobs/from_extension`;

      console.log(`Sending markdown to backend API: ${apiUrl}`);

      try {
        const response = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            // Add any other headers like Authorization if needed in the future
          },
          body: JSON.stringify({ markdown_content: markdownContent }),
        });

        if (response.ok) {
          const responseData = await response.json(); // Assuming backend returns the saved job details
          console.log("Backend API call successful:", responseData);
          // Show success notification
          chrome.notifications.create({
            type: 'basic',
            iconUrl: 'icons/icon48.png',
            title: 'Great Fit Saver',
            message: `Job "${responseData.title || 'Unknown'}" saved successfully!`, // Use title from response if available
            priority: 0
          });
        } else {
          // Handle API errors (e.g., 4xx, 5xx)
          let errorDetail = `HTTP error! Status: ${response.status}`;
          try {
            const errorData = await response.json();
            errorDetail = errorData.detail || JSON.stringify(errorData);
          } catch (e) {
             // Could not parse error JSON, use status text
             errorDetail = response.statusText;
          }
          console.error("Backend API call failed:", response.status, errorDetail);
          chrome.notifications.create({
            type: 'basic',
            iconUrl: 'icons/icon48.png',
            title: 'Great Fit Saver Error',
            message: `Failed to save job: ${errorDetail}`,
            priority: 1
          });
        }
      } catch (networkError) {
        // Handle network errors (e.g., server unreachable)
        console.error("Network error calling backend API:", networkError);
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icons/icon48.png',
          title: 'Great Fit Saver Error',
          message: `Network Error: Could not connect to the server. Is it running?`, // More specific message
          priority: 1
        });
      }
      // ---- END API Call ----

    } else {
      console.warn(
        "Script injection succeeded, but no markdown result returned.",
      );
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon48.png',
        title: 'Great Fit Saver',
        message: 'Could not find job content on the page.',
        priority: 1
      });
    }
  } catch (err) {
    console.error(`Failed to execute script or handle result: ${err}`, err);
    chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon48.png',
        title: 'Great Fit Saver Error',
        message: `An unexpected error occurred: ${err.message}`,
        priority: 1
    });
  }
});

console.log("Background service worker started and listener added.");
