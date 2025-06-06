/**
 * upload.js - Resume upload functionality
 * Handles resume file uploads and processing
 */

// Function to upload the resume file
async function uploadResumeFile() {
  console.log("Uploading resume file...");
  const fileInput = document.getElementById("resumeFile");
  const file = fileInput.files[0];
  const uploadStatusElement = document.getElementById("uploadStatus");
  const uploadContent = document.getElementById("uploadContent");
  const uploadSpinner = document.getElementById("uploadSpinner");
  const uploadArea = document.getElementById("uploadArea");
  const resumeUploadContainer = document.getElementById("resumeUploadContainer");
  const resetProfileContainer = document.getElementById("profileActions");

  if (!file) {
    showToast('Please select a file to upload.', 'warning');
    return;
  }

  // Check file type
  const allowedTypes = [".pdf", ".docx", ".doc", ".txt"];
  const fileExtension = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
  if (!allowedTypes.includes(fileExtension)) {
    showToast('Invalid file type. Please upload a PDF, Word, or TXT file.', 'error');
    return;
  }

  try {
    // Show spinner, hide original content
    if (uploadArea) {
      if (uploadContent) uploadContent.classList.add("hidden");
      if (uploadSpinner) uploadSpinner.classList.remove("hidden");
      uploadArea.classList.remove("hover:border-indigo-600", "hover:bg-indigo-100"); // Disable hover effect during processing
    }
    if (uploadStatusElement) {
      uploadStatusElement.textContent = ''; // Clear previous status text
    }

    // Use current user id from global set by auth.js
    const userId = window.currentUserId;

    // Create form data
    const formData = new FormData();
    formData.append("resume", file);

    // Upload file
    const response = await fetch(`/resume/upload`, {
      method: "POST",
      body: formData,
      headers: await window.authHeaders(),
    });

    // Handle response
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log("Resume processed successfully:", data);
    showToast('Resume processed successfully!', 'success');

    // Hide upload container, show reset button
    if (resumeUploadContainer) {
      resumeUploadContainer.style.display = "none";
    }
    if (resetProfileContainer) {
      resetProfileContainer.style.display = "block";
    }

    // Fetch and display the profile
    await loadProfile();
  } catch (error) {
    console.error("Error uploading resume:", error);

    // Restore the upload area
    if (uploadArea) {
      if (uploadContent) uploadContent.classList.remove("hidden");
      if (uploadSpinner) uploadSpinner.classList.add("hidden");
      uploadArea.classList.add("hover:border-indigo-600", "hover:bg-indigo-100"); // Re-enable hover effect
    }

    // Show error message
    showToast(`Error processing resume: ${error.message}`, 'error');
  }
}

// Function to reset the file upload
function resetFileUpload() {
  const fileInput = document.getElementById("resumeFile");
  const uploadStatusElement = document.getElementById("uploadStatus");
  const uploadArea = document.getElementById("uploadArea");
  const uploadContent = document.getElementById("uploadContent");
  const uploadSpinner = document.getElementById("uploadSpinner");

  // Clear the file input
  if (fileInput) {
    fileInput.value = "";
  }

  // Clear any status messages
  if (uploadStatusElement) {
    uploadStatusElement.innerHTML = "";
  }

  // Restore the upload area if it was hidden
  if (uploadArea) {
    if (uploadContent) uploadContent.classList.remove("hidden");
    if (uploadSpinner) uploadSpinner.classList.add("hidden");
    uploadArea.classList.add("hover:border-indigo-600", "hover:bg-indigo-100"); // Re-enable hover effect
  }

  // Remove any custom file name display
  const customFileDisplay = document.getElementById("customFileDisplay");
  if (customFileDisplay) {
    customFileDisplay.innerHTML = "";
    customFileDisplay.style.display = "none";
  }
}

// Initialize custom file upload functionality
function initializeFileUpload() {
  const uploadArea = document.getElementById("uploadArea");
  const fileInput = document.getElementById("resumeFile");

  if (!uploadArea || !fileInput) {
    console.error("Upload elements (uploadArea or resumeFile) not found on initial attempt. Cannot initialize file upload.");
    // Optionally, you could re-introduce a single retry here if the 100ms DOMContentLoaded timeout isn't always enough,
    // but the goal is to remove the complex internal retry loop from the original function.
    // For now, let's assume the DOMContentLoaded timeout is the primary mechanism.
    return;
  }
  // Proceed with initializeUploadEventHandlers directly
  initializeUploadEventHandlers(uploadArea, fileInput);
}

// Setup event handlers for the upload functionality
function initializeUploadEventHandlers(uploadArea, fileInput) {

  if (uploadArea.dataset.uploadHandlersInitialized) {
    console.log("Upload event handlers already initialized for this area. Skipping.");
    return;
  }
  uploadArea.dataset.uploadHandlersInitialized = "true";
  console.log("Initializing upload event handlers");

  // Make the upload area clickable
  uploadArea.addEventListener("click", function() {
    fileInput.click();
  });

  // Handle file selection change
  fileInput.addEventListener("change", function() {
    const file = fileInput.files[0];

    if (file) {
      console.log("File selected:", file.name);

      // Auto-process the resume immediately
      uploadResumeFile();
    }
  });

  // Setup drag and drop
  uploadArea.addEventListener("dragover", function(e) {
    e.preventDefault();
    uploadArea.classList.add("border-indigo-600", "bg-indigo-100", "ring-2", "ring-indigo-300"); // Use Tailwind classes for visual feedback
  });

  uploadArea.addEventListener("dragleave", function() {
    uploadArea.classList.remove("border-indigo-600", "bg-indigo-100", "ring-2", "ring-indigo-300");
  });

  uploadArea.addEventListener("drop", function(e) {
    e.preventDefault();
    uploadArea.classList.remove("border-indigo-600", "bg-indigo-100", "ring-2", "ring-indigo-300"); // Remove styles on drop

    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      // Trigger the change event
      const event = new Event('change', { bubbles: true });
      fileInput.dispatchEvent(event);
    }
  });
}

// Make sure we initialize after DOM content is loaded
document.addEventListener("DOMContentLoaded", function() {
  console.log("DOMContentLoaded: Initializing file upload functionality");
  setTimeout(() => {
    initializeFileUpload();
  }, 100); // Small delay to ensure Alpine.js has initialized components
});
