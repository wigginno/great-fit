/**
 * core.js - Core initialization and setup
 * Contains the main initialization logic and event binding
 */
/**
 * core.js - Core initialization and setup
 * Contains the main initialization logic and event binding
 */

document.addEventListener("DOMContentLoaded", function () {
  // Hide saved jobs section initially
  const savedJobsSection = document.getElementById("savedJobsSection");
  if (savedJobsSection) {
    savedJobsSection.classList.add("hidden");
  }

  // Set up event listeners for form submissions
  setupEventListeners();

  // Initialize the file upload functionality
  initializeFileUpload();

  // Wait for auth.js to fetch the user, then load profile & SSE
  const waitForUser = () => {
    if (window.currentUserId) {
      loadProfile();
      // connectToSSE handled in sse.js auto-connect
    } else {
      setTimeout(waitForUser, 250);
    }
  };
  waitForUser();
});

// Provide a global showToast helper early so other modules can use it before ui.js loads.
// Once ui.js is parsed it will overwrite this with the full Alpine-powered version.
if (!window.showToast) {
  window.showToast = function (message, type = 'info', duration = 4000) {
    document.dispatchEvent(
      new CustomEvent('toast', { detail: { message, type, duration } })
    );
  };
}

// currentUserId will be set by auth.js after fetching /users/me
