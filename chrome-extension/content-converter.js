(function () {
  console.log("Content converter script injected.");
  console.log("Content script loaded.");

  // Use an IIFE to execute and return the result directly
  return (async () => {
    // Check if Turndown is loaded
    if (typeof TurndownService === "undefined") {
      console.error("Turndown library not loaded.");
      return { error: "Turndown library not loaded." }; // Return error object
    }
    console.log("Turndown library loaded successfully.");

    try {
      // Initialize Turndown service with options (optional)
      const turndownService = new TurndownService({
        headingStyle: "atx", // Use '#' for headers
        hr: "---", // Use '---' for horizontal rules
        bulletListMarker: "*", // Use '*' for bullet points
        codeBlockStyle: "fenced", // Use fenced code blocks
        emDelimiter: "_", // Use '_' for emphasis
        strongDelimiter: "**", // Use '**' for strong
        linkStyle: "inlined", // Use inline links
      });
      console.log("Turndown service initialized.");

      // --- ADD RULES TO REMOVE UNWANTED TAGS ---
      turndownService.remove([
        "script",
        "style",
        "noscript",
        "iframe",
        "link",
        "meta",
      ]);
      console.log(
        "Added rules to remove script, style, noscript, iframe, link, and meta tags.",
      );
      // --------------------------------------------

      // Add custom filtering function to avoid large JSON blobs
      turndownService.addRule("removeJsonBlobs", {
        filter: function (node) {
          // Check for potential JSON blobs in various contexts
          // 1. Check for pre tags with large content that could be JSON
          if (
            node.nodeName === "PRE" &&
            node.textContent.length > 1000 &&
            (node.textContent.trim().startsWith("{") ||
              node.textContent.trim().startsWith("["))
          ) {
            return true;
          }

          // 2. Check for code blocks with JSON
          if (
            node.nodeName === "CODE" &&
            node.textContent.length > 1000 &&
            (node.textContent.trim().startsWith("{") ||
              node.textContent.trim().startsWith("["))
          ) {
            return true;
          }

          // 3. Check for hidden divs that might contain data
          if (
            (node.nodeName === "DIV" || node.nodeName === "SPAN") &&
            (node.style.display === "none" ||
              node.style.visibility === "hidden") &&
            node.textContent.length > 500
          ) {
            return true;
          }

          // 4. Check for data attributes that might contain JSON
          if (node.attributes && node.attributes.length > 0) {
            for (let i = 0; i < node.attributes.length; i++) {
              const attr = node.attributes[i];
              if (
                attr.name.startsWith("data-") &&
                attr.value.length > 500 &&
                (attr.value.includes("{") || attr.value.includes("["))
              ) {
                // Remove the attribute instead of the whole node
                node.removeAttribute(attr.name);
              }
            }
          }

          return false;
        },
        replacement: function () {
          // Return empty string to remove the content
          return "";
        },
      });

      // Function to clean the DOM before processing
      function cleanDOM(element) {
        const clonedElement = element.cloneNode(true);

        // Remove comments which might contain data
        const commentIterator = document.createNodeIterator(
          clonedElement,
          NodeFilter.SHOW_COMMENT,
        );
        let commentNode;
        while ((commentNode = commentIterator.nextNode())) {
          commentNode.parentNode.removeChild(commentNode);
        }

        // Remove any elements with JSON-like content
        const allElements = clonedElement.querySelectorAll("*");
        for (let i = 0; i < allElements.length; i++) {
          const el = allElements[i];

          // Check for inline JSON in data attributes
          if (el.attributes) {
            for (let j = 0; j < el.attributes.length; j++) {
              const attr = el.attributes[j];
              if (
                attr.name.startsWith("data-") &&
                attr.value.length > 500 &&
                (attr.value.includes("{") || attr.value.includes("["))
              ) {
                el.removeAttribute(attr.name);
              }
            }
          }

          // Check for inline onclick/onload handlers that might contain data
          if (el.hasAttribute("onclick") || el.hasAttribute("onload")) {
            el.removeAttribute("onclick");
            el.removeAttribute("onload");
          }
        }

        return clonedElement;
      }

      console.log("Getting page HTML...");

      // Get a clean clone of the body to work with
      const cleanedBody = cleanDOM(document.body);
      const htmlContent = cleanedBody.innerHTML;

      console.log("Cleaned HTML:", htmlContent.substring(0, 500) + "..."); // Log start of HTML
      console.log("HTML content length:", htmlContent.length);

      console.log(">>> BEFORE Turndown conversion call <<<");
      // Convert HTML to Markdown using Turndown
      const markdownContent = turndownService.turndown(htmlContent);
      console.log(">>> AFTER Turndown conversion call <<<");

      console.log(
        "Converted Markdown (content script log):",
        markdownContent.substring(0, 500) + "...",
      ); // Log start of Markdown
      console.log("Markdown generated, length:", markdownContent.length);

      // Send the Markdown content back to the background script
      // The last expression evaluated in the script is its return value
      return markdownContent;
    } catch (error) {
      console.error("Error during HTML to Markdown conversion:", error);
      // Optionally send error back
      return { error: `Conversion Error: ${error.message}` }; // Return error object
    }
  })();
})(); // Immediately invoked function expression (IIFE) to avoid polluting global scope
