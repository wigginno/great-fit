/**
 * profile.js - Profile management functionality
 * Handles loading, displaying, and managing the user profile
 */

// Function to load and display user profile
async function loadProfile() {
  try {
    // Use currentUserId globally
    const userId = window.currentUserId;

    const response = await fetch(`/profile/`, { headers: { ...window.authHeaders() } });

    if (response.status === 204) {
      // No profile yet — keep upload UI visible
      console.info("No profile found for user", userId);
      return;
    }

    if (!response.ok) {
      let msg = `HTTP error! status: ${response.status}`;
      try {
        const errJson = await response.json();
        msg = errJson.detail || msg;
      } catch (_) {
        /* ignore */
      }
      throw new Error(msg);
    }

    const responseData = await response.json();

    // Extract profile_data from the response - this is the actual profile data
    const profileData = responseData.profile_data;

    // Show the profile action buttons
    const profileActions = document.getElementById("profileActions");
    if (profileActions) profileActions.classList.remove("hidden");

    // Hide the resume upload container
    const resumeUploadContainer = document.getElementById("resumeUploadContainer");
    if (resumeUploadContainer) {
      resumeUploadContainer.style.display = "none";
    }
    // Also hide the entire upload section wrapper to remove empty space
    const resumeUploadSection = document.getElementById("resumeUploadSection");
    if (resumeUploadSection) resumeUploadSection.style.display = "none";

    // Show Saved Jobs section
    const savedJobsSection = document.getElementById("savedJobsSection");
    if (savedJobsSection) {
      savedJobsSection.classList.remove("hidden");
      // Load jobs list once the section is visible
      if (typeof loadJobs === "function") {
        loadJobs();
      }
    }

    // Format the profile data and populate modal content
    const formattedProfile = formatProfileData(profileData);
    const profileModalContent = document.getElementById("profileModalContent");
    if (profileModalContent) {
      profileModalContent.innerHTML = formattedProfile;
    }
  } catch (error) {
    console.error("Error loading profile:", error);
  }
}

// Function to reset the profile section to allow re-upload
function resetProfile() {
  // Get containers
  const profileActions = document.getElementById("profileActions");

  // Hide saved jobs 
  const savedJobsSection = document.getElementById("savedJobsSection");
  if (savedJobsSection) savedJobsSection.classList.add("hidden");

  // Hide modal if open
  const profileModal = document.getElementById("profileModal");
  if (profileModal) {
    profileModal.classList.add("hidden");
    profileModal.classList.remove("flex");
  }

  // Show upload section and hide profile actions
  const resumeUploadSection = document.getElementById("resumeUploadSection");
  if (resumeUploadSection) resumeUploadSection.style.display = "block";
  const resumeUploadContainer = document.getElementById("resumeUploadContainer");
  if (resumeUploadContainer) resumeUploadContainer.style.display = "block";
  if (profileActions) profileActions.classList.add("hidden");

  // Clear previous file input state
  if (typeof resetFileUpload === 'function') {
    resetFileUpload();
  }
}
