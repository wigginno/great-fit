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

  // Initially we don't have profile - loadProfile will reveal sections when appropriate
  loadProfile();

  // Set up event listeners for form submissions
  setupEventListeners();

  // Initialize the file upload functionality
  initializeFileUpload();

  // Connect to SSE for real-time job updates
  connectToSSE(window.currentUserId);
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

// Expose current user id globally so other modules can read a single source of truth
// In production this should be injected server‑side.
if (window.currentUserId === undefined) {
  window.currentUserId = 1;
}
