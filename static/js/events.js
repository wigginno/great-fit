/**
 * events.js - Event handling setup
 * Centralizes event listener setup for the application
 */

// Set up all event listeners
function setupEventListeners() {
  // Job list container for job clicking
  const jobsList = document.getElementById("jobsList");
  if (jobsList) {
    jobsList.addEventListener("click", handleJobClick);
  }

  // Job details container for ranking
  const jobDetails = document.getElementById("jobDetails");
  if (jobDetails) {
    // jobDetails.addEventListener("click", handleJobActions); // Removed as per issue 9.1
  }

  // Reset profile button
  const resetProfileButton = document.getElementById("resetProfileButton");
  if (resetProfileButton) {
    resetProfileButton.addEventListener("click", resetProfile);
  }

  // View Profile button - now dispatches an event for Alpine to handle
  const viewProfileButton = document.getElementById("viewProfileButton");
  if (viewProfileButton) {
    viewProfileButton.addEventListener("click", function() {
      window.dispatchEvent(new CustomEvent('open-profile-modal'));
    });
  }
  // Close profile modal button is handled by Alpine via @click="show = false" or @click.away

  // Add Job button - now dispatches an event for Alpine to handle
  const addJobBtn = document.getElementById("add-job-btn");
  if (addJobBtn) {
    addJobBtn.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent('open-add-job-modal'));
    });
  }

  // Modal save and cancel buttons
  const modalSaveBtn = document.getElementById("modal-save-btn");
  const modalCancelBtn = document.getElementById("modal-cancel-btn"); // This button is now handled by Alpine in the template

  if (modalSaveBtn) {
    modalSaveBtn.addEventListener("click", saveModalJob);
  }
  // The old event listeners for opening/closing modals via classList manipulation
  // and window click are removed as Alpine.js handles this more declaratively.
}

// Already called from core.js, no need for second DOMContentLoaded listener
