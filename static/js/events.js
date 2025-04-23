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
    jobDetails.addEventListener("click", handleJobActions);
  }

  // Reset profile button
  const resetProfileButton = document.getElementById("resetProfileButton");
  if (resetProfileButton) {
    resetProfileButton.addEventListener("click", resetProfile);
  }

  // View Profile button and modal
  const viewProfileButton = document.getElementById("viewProfileButton");
  const profileModal = document.getElementById("profileModal");
  const closeProfileModalBtn = document.getElementById("closeProfileModal");
  if (viewProfileButton && profileModal) {
    viewProfileButton.addEventListener("click", function() {
      profileModal.classList.remove("hidden");
      profileModal.classList.add("flex");
    });
  }
  if (closeProfileModalBtn && profileModal) {
    closeProfileModalBtn.addEventListener("click", function() {
      profileModal.classList.add("hidden");
      profileModal.classList.remove("flex");
    });
  }

  // Modal Elements
  const addJobModal = document.getElementById("add-job-modal");
  const addJobBtn = document.getElementById("add-job-btn");

  if (addJobModal && addJobBtn) {
    const closeModalBtn = addJobModal.querySelector(".close-btn");
    const modalSaveBtn = document.getElementById("modal-save-btn");
    const modalCancelBtn = document.getElementById("modal-cancel-btn");

    // Open Modal
    addJobBtn.addEventListener("click", () => {
      addJobModal.classList.remove("hidden");
      addJobModal.classList.add("flex");
    });

    // Close Modal via Close button (X)
    if (closeModalBtn) {
      closeModalBtn.addEventListener("click", () => {
        addJobModal.classList.add("hidden");
        addJobModal.classList.remove("flex");
      });
    }

    // Close Modal via Cancel button
    if (modalCancelBtn) {
      modalCancelBtn.addEventListener("click", () => {
        addJobModal.classList.add("hidden");
        addJobModal.classList.remove("flex");
      });
    }

    // Close Modal by clicking outside the modal content
    window.addEventListener("click", (event) => {
      if (event.target === addJobModal) {
        addJobModal.classList.add("hidden");
        addJobModal.classList.remove("flex");
      }
    });

    // Save Job from Modal
    if (modalSaveBtn) {
      modalSaveBtn.addEventListener("click", saveModalJob);
    }
  }
}

// Already called from core.js, no need for second DOMContentLoaded listener
