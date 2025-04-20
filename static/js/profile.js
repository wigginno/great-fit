/**
 * profile.js - Profile management functionality
 * Handles loading, displaying, and managing the user profile
 */

// Function to load and display user profile
async function loadProfile() {
  try {
    // For now, hardcode user ID to 1
    const userId = 1;
    const profileContainer = document.getElementById("userProfile");
    
    if (!profileContainer) {
      console.error("Profile container not found");
      return;
    }
    
    profileContainer.innerHTML = '<p class="loading">Loading profile...</p>';
    
    const response = await fetch(`/users/${userId}/profile/`);
    
    if (response.status === 204) {
      // No profile exists yet
      profileContainer.innerHTML = '<p class="placeholder">Your profile will appear here. Upload your resume to get started.</p>';
      return;
    }
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }
    
    const responseData = await response.json();
    
    // Extract profile_data from the response - this is the actual profile data
    const profileData = responseData.profile_data;
    
    if (!profileData || Object.keys(profileData).length === 0) {
      profileContainer.innerHTML = '<p class="placeholder">Your profile will appear here. Upload your resume to get started.</p>';
      return;
    }
    
    // Show the reset button once we have a profile
    const resetProfileContainer = document.getElementById("resetProfileContainer");
    if (resetProfileContainer) {
      resetProfileContainer.style.display = "block";
    }
    
    // Hide the resume upload container
    const resumeUploadContainer = document.getElementById("resumeUploadContainer");
    if (resumeUploadContainer) {
      resumeUploadContainer.style.display = "none";
    }
    
    // Format the profile data using the profile formatter
    const formattedProfile = formatProfileData(profileData);
    profileContainer.innerHTML = formattedProfile;
    
    // No need to add additional collapsible functionality - Bootstrap handles this
    // The collapsible headers and content are already in the markup from profileFormatter.js
  } catch (error) {
    console.error("Error loading profile:", error);
    const profileContainer = document.getElementById("userProfile");
    if (profileContainer) {
      profileContainer.innerHTML = `<p class="error">Error loading profile: ${error.message}</p>`;
    }
  }
}

// Function to reset the profile section to allow re-upload
function resetProfile() {
  // Get containers
  const resumeUploadContainer = document.getElementById("resumeUploadContainer");
  const resetProfileContainer = document.getElementById("resetProfileContainer");
  const profileContainer = document.getElementById("userProfile");
  
  // Show upload, hide reset button
  if (resumeUploadContainer) {
    resumeUploadContainer.style.display = "block";
  }
  if (resetProfileContainer) {
    resetProfileContainer.style.display = "none";
  }
  
  // Clear profile
  if (profileContainer) {
    profileContainer.innerHTML = '<p class="placeholder">Your profile will appear here. Upload your resume to get started.</p>';
  }
}

// Function to expand all profile sections
function expandAllProfileSections() {
  const profileContainer = document.getElementById("userProfile");
  if (!profileContainer) return;
  
  // Get all collapsible elements
  const collapseElements = profileContainer.querySelectorAll('.collapse');
  collapseElements.forEach(collapse => {
    // Add the 'show' class directly to expand the section
    collapse.classList.add('show');
    
    // Find the corresponding header and update its aria-expanded attribute
    const headerId = collapse.getAttribute('aria-labelledby');
    if (headerId) {
      const header = document.getElementById(headerId);
      if (header) {
        header.setAttribute('aria-expanded', 'true');
      }
    }
  });
}

// Function to collapse all profile sections
function collapseAllProfileSections() {
  const profileContainer = document.getElementById("userProfile");
  if (!profileContainer) return;
  
  // Get all collapsible elements
  const collapseElements = profileContainer.querySelectorAll('.collapse');
  collapseElements.forEach(collapse => {
    // Remove the 'show' class directly to collapse the section
    collapse.classList.remove('show');
    
    // Find the corresponding header and update its aria-expanded attribute
    const headerId = collapse.getAttribute('aria-labelledby');
    if (headerId) {
      const header = document.getElementById(headerId);
      if (header) {
        header.setAttribute('aria-expanded', 'false');
      }
    }
  });
}
