/**
 * events.js - Event handling setup
 * Centralizes event listener setup for the application
 */

// Set up all event listeners
function setupEventListeners() {
  // Upload and clear buttons for resume
  const uploadResumeButton = document.getElementById("uploadResumeButton");
  if (uploadResumeButton) {
    uploadResumeButton.addEventListener("click", uploadResumeFile);
  }

  const clearUploadButton = document.getElementById("clearUploadButton");
  if (clearUploadButton) {
    clearUploadButton.addEventListener("click", clearResumeUpload);
  }

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

  // Event delegation for profile controls (Expand/Collapse All)
  const userProfileContainer = document.getElementById("userProfile");
  if (userProfileContainer) {
    userProfileContainer.addEventListener("click", function(event) {
      const expandButton = event.target.closest('#expandAllProfile');
      const collapseButton = event.target.closest('#collapseAllProfile');

      if (expandButton) {
        event.preventDefault(); // Prevent default link behavior (#)
        expandAllProfileSections();
      } else if (collapseButton) {
        event.preventDefault(); // Prevent default link behavior (#)
        collapseAllProfileSections();
      }
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
      addJobModal.style.display = "block";
    });

    // Close Modal via Close button (X)
    if (closeModalBtn) {
      closeModalBtn.addEventListener("click", () => {
        addJobModal.style.display = "none";
      });
    }

    // Close Modal via Cancel button
    if (modalCancelBtn) {
      modalCancelBtn.addEventListener("click", () => {
        addJobModal.style.display = "none";
      });
    }

    // Close Modal by clicking outside the modal content
    window.addEventListener("click", (event) => {
      if (event.target == addJobModal) {
        addJobModal.style.display = "none";
      }
    });

    // Save Job from Modal
    if (modalSaveBtn) {
      modalSaveBtn.addEventListener("click", saveModalJob);
    }
  }
}
