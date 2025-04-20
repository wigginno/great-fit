/**
 * core.js - Core initialization and setup
 * Contains the main initialization logic and event binding
 */

document.addEventListener("DOMContentLoaded", function () {
  // Load initial data
  loadProfile();
  loadJobs();

  // Set up event listeners for form submissions
  setupEventListeners();

  // Initialize the file upload functionality
  initializeFileUpload();

  // Connect to SSE for real-time job updates (assuming user ID 1 for now)
  connectToSSE(1);
});

// Toast notification system
function showToast(message, type = 'success') {
  // Create toast container if it doesn't exist
  let toastContainer = document.getElementById('toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    document.body.appendChild(toastContainer);
  }

  // Create toast element
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  
  // Add to container
  toastContainer.appendChild(toast);
  
  // Remove after animation
  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => {
      toast.remove();
    }, 500);
  }, 3000);
}
