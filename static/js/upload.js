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
  const uploadArea = document.getElementById("uploadArea");
  const resumeUploadContainer = document.getElementById("resumeUploadContainer");
  const resetProfileContainer = document.getElementById("resetProfileContainer");
  const userProfileContainer = document.getElementById("userProfile");

  if (!file) {
    uploadStatusElement.innerHTML = '<div class="alert alert-warning">Please select a file to upload.</div>';
    return;
  }

  // Check file type
  const allowedTypes = [".pdf", ".docx", ".doc", ".txt"];
  const fileExtension = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
  if (!allowedTypes.includes(fileExtension)) {
    uploadStatusElement.innerHTML = '<div class="alert alert-danger">Invalid file type. Please upload a PDF, Word, or TXT file.</div>';
    return;
  }

  try {
    // Hide the upload area during processing
    if (uploadArea) {
      uploadArea.style.display = "none";
    }
    
    // Show loading status
    uploadStatusElement.innerHTML = '<div class="alert alert-info">Processing resume... <div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">Loading...</span></div></div>';

    // For now, hardcode user ID to 1
    const userId = 1;

    // Create form data
    const formData = new FormData();
    formData.append("resume", file);

    // Upload file
    const response = await fetch(`/users/${userId}/resume/upload`, {
      method: "POST",
      body: formData
    });

    // Handle response
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log("Resume processed successfully:", data);

    // Hide upload container, show reset button
    if (resumeUploadContainer) {
      resumeUploadContainer.style.display = "none";
    }
    if (resetProfileContainer) {
      resetProfileContainer.style.display = "block";
    }

    // Clear any previous profile and show loading message
    if (userProfileContainer) {
      userProfileContainer.innerHTML = '<p class="loading">Loading profile...</p>';
    }

    // Fetch and display the profile
    await loadProfile();
  } catch (error) {
    console.error("Error uploading resume:", error);
    
    // Restore the upload area
    if (uploadArea) {
      uploadArea.style.display = "block";
    }
    
    // Show error message
    uploadStatusElement.innerHTML = `<div class="alert alert-danger">Error processing resume: ${error.message}</div>`;
  }
}

// Function to reset the file upload
function resetFileUpload() {
  const fileInput = document.getElementById("resumeFile");
  const uploadStatusElement = document.getElementById("uploadStatus");
  const uploadArea = document.getElementById("uploadArea");

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
    uploadArea.style.display = "block";
  }

  // Remove any custom file name display
  const customFileDisplay = document.getElementById("customFileDisplay");
  if (customFileDisplay) {
    customFileDisplay.innerHTML = "";
    customFileDisplay.style.display = "none";
  }
}

// For backward compatibility
function clearResumeUpload() {
  resetFileUpload();
}

// Initialize custom file upload functionality
function initializeFileUpload() {
  const uploadArea = document.getElementById("uploadArea");
  const fileInput = document.getElementById("resumeFile");

  if (!uploadArea || !fileInput) {
    console.error("Upload elements not found");
    return;
  }

  // Make the upload area clickable
  uploadArea.addEventListener("click", function() {
    fileInput.click();
  });

  // Handle file selection change
  fileInput.addEventListener("change", function() {
    const file = fileInput.files[0];
    
    if (file) {
      console.log("File selected:", file.name);
      
      // Hide the upload area - no need to show file info
      uploadArea.style.display = "none";
      
      // Auto-process the resume immediately
      uploadResumeFile();
    }
  });

  // Setup drag and drop
  uploadArea.addEventListener("dragover", function(e) {
    e.preventDefault();
    uploadArea.classList.add("dragover");
  });

  uploadArea.addEventListener("dragleave", function() {
    uploadArea.classList.remove("dragover");
  });

  uploadArea.addEventListener("drop", function(e) {
    e.preventDefault();
    uploadArea.classList.remove("dragover");
    
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      // Trigger the change event
      const event = new Event('change', { bubbles: true });
      fileInput.dispatchEvent(event);
    }
  });
}
