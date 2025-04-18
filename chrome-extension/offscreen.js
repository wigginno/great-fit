// Listen for messages from the background script
chrome.runtime.onMessage.addListener(handleMessages);

async function handleMessages(message) {
  // Return early if this message isn't meant for the offscreen document.
  if (message.target !== "offscreen-doc") {
    return;
  }

  // Dispatch the message to an appropriate handler.
  switch (message.type) {
    case "copy-to-clipboard":
      console.log("Offscreen document received copy request.");
      handleClipboardWrite(message.data);
      break;
    default:
      console.warn(`Unexpected message type received: '${message.type}'.`);
  }
}

// Use the Clipboard API to write the data passed from the background script.
async function handleClipboardWrite(data) {
  // Workaround using document.execCommand('copy')
  const textarea = document.createElement("textarea");
  textarea.value = data;
  textarea.style.position = "absolute"; // Prevent scrolling page
  textarea.style.left = "-9999px"; // Move offscreen
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand("copy");
    console.log(
      "Text successfully copied to clipboard by offscreen document (using execCommand).",
    );
  } catch (error) {
    console.error(
      `Offscreen document failed to copy text using execCommand. Error Name: ${error.name}, Message: ${error.message}`,
    );
  } finally {
    document.body.removeChild(textarea);
    // Close the offscreen document automatically after attempting the copy.
    // Adjust timeout as needed, or use message passing for confirmation before closing.
    // setTimeout(() => { window.close(); }, 1000); // Close after 1 second
    // For simplicity now, we'll let the background script manage closing later if needed.
  }
}
