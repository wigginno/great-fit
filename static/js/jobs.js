/**
 * jobs.js - Job management functionality
 * Handles loading, displaying, and managing job listings
 */

// Function to load and display jobs
async function loadJobs() {
  try {
    const userId = window.currentUserId;
    const jobsContainer = document.getElementById("jobsList");
    jobsContainer.innerHTML = "Loading jobs...";

    const response = await fetch(`/users/${userId}/jobs/`, { headers: { ...window.authHeaders() } });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(
        errorData.detail || `HTTP error! status: ${response.status}`,
      );
    }

    const jobs = await response.json();

    if (jobs.length === 0) {
      jobsContainer.innerHTML =
        '<p class="placeholder">No jobs saved yet. Add a job using the form above.</p>';
      return;
    }

    let jobsHtml = '<div class="jobs-list">';

    jobs.forEach((job) => {
      jobsHtml += `
                <div class="job-card relative rounded-lg bg-white border border-gray-200 shadow-sm p-4 hover:shadow-md transition cursor-pointer" data-job-id="${job.id}">
                    <button class="delete-job-btn absolute top-2 right-2 text-red-500 hover:text-red-700" data-job-id="${job.id}" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                    <div class="job-title font-medium text-gray-800">${job.title || "Untitled Job"}</div>
                    <div class="job-company text-sm text-gray-500">${job.company || "Unknown Company"}</div>
                    ${
                      job.ranking_score !== null && job.ranking_score !== undefined
                        ? `<div class="job-score mt-2 inline-block rounded px-2 py-0.5 text-xs font-semibold text-white">Match: ${job.ranking_score.toFixed(1)}/10</div>`
                        : '<div class="job-score mt-2 inline-block rounded px-2 py-0.5 text-xs font-semibold text-white unranked">Scoring job...</div>'
                    }
                </div>
            `;
    });

    jobsHtml += "</div>";
    jobsContainer.innerHTML = jobsHtml;

    // Add color-coding classes after rendering
    jobsContainer.querySelectorAll(".job-card").forEach((card) => {
      const jobId = card.getAttribute("data-job-id");
      const job = jobs.find((j) => j.id == jobId); // Find the corresponding job data
      if (job) {
        const scoreElement = card.querySelector(".job-score");
        if (
          scoreElement &&
          job.ranking_score !== null &&
          job.ranking_score !== undefined
        ) {
          // Gradient-based color mapping
          const clamped = Math.max(0, Math.min(10, job.ranking_score));
          const hue = (clamped / 10) * 120;
          scoreElement.style.backgroundColor = `hsl(${hue}, 90%, 45%)`;
          scoreElement.style.color = "white";
          scoreElement.style.padding = "0.1rem 0.4rem";
          scoreElement.style.borderRadius = "0.25rem";
          scoreElement.style.display = "inline-block";
        } else if (
          scoreElement &&
          scoreElement.classList.contains("unranked")
        ) {
          scoreElement.style.backgroundColor = "#6c757d"; // Default grey for unranked
          scoreElement.style.color = "white";
          scoreElement.style.padding = "0.1rem 0.4rem";
          scoreElement.style.borderRadius = "0.25rem";
          scoreElement.style.display = "inline-block";
        }
      }
    });
  } catch (error) {
    console.error("Error loading jobs:", error);
    const jobsContainer = document.getElementById("jobsList");
    jobsContainer.innerHTML = `<p class="error">Error loading jobs: ${error.message}</p>`;
  }
}

// Function to save job from modal
async function saveModalJob() {
  const modalJobTitle = document.getElementById("modal-job-title");
  const modalJobCompany = document.getElementById("modal-job-company");
  const modalJobDescription = document.getElementById("modal-job-description");
  const modalSaveBtn = document.getElementById("modal-save-btn");
  const modalCancelBtn = document.getElementById("modal-cancel-btn");
  const modalLoadingIndicator = document.getElementById("modal-loading-indicator");
  const addJobModal = document.getElementById("add-job-modal");

  // Validation - Description is required
  if (!modalJobDescription.value.trim()) {
    const errorDiv = document.getElementById("modal-error") || document.createElement("div");
    errorDiv.id = "modal-error";
    errorDiv.className = "mt-3 text-sm text-red-600";

    if (!document.getElementById("modal-error")) {
      modalJobDescription.after(errorDiv);
    }
    return;
  }

  try {
    // Afficher immédiatement le compteur +1
    const current = parseInt(document.getElementById('savingIndicatorText').dataset.count || '0', 10);
    updateProcessingIndicator(current + 1);

    // Disable buttons and show loading
    modalSaveBtn.disabled = true;
    modalCancelBtn.disabled = true;
    modalLoadingIndicator.style.display = "inline-block";

    // Remove any previous error message
    const errorDiv = document.getElementById("modal-error");
    if (errorDiv) {
      errorDiv.remove();
    }

    const userId = window.currentUserId;

    // Payload attendu par l’endpoint backend
    const payload = {
      markdown_content: modalJobDescription.value,
    };

    // Appel de l’endpoint POST /jobs/from_extension
    const response = await fetch(`/users/${userId}/jobs/from_extension`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...window.authHeaders(),
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    // Close modal
    addJobModal.style.display = "none";

    // Show success message (le SSE créera la carte lorsqu’elle sera prête)
    showToast("Job submitted – processing in background...");

    // Reset form (don't reload jobs - SSE will handle this)
    modalJobTitle.value = "";
    modalJobCompany.value = "";
    modalJobDescription.value = "";

  } catch (error) {
    console.error("Error saving job:", error);

    // Show error in modal
    const errorDiv = document.getElementById("modal-error") || document.createElement("div");
    errorDiv.id = "modal-error";
    errorDiv.className = "mt-3 text-sm text-red-600";

    if (!document.getElementById("modal-error")) {
      modalJobDescription.after(errorDiv);
    }
    errorDiv.textContent = `Error saving job: ${error.message}`;
  } finally {
    // Re-enable buttons and hide loading
    modalSaveBtn.disabled = false;
    modalCancelBtn.disabled = false;
    modalLoadingIndicator.style.display = "none";
  }
}

// Function to handle clicking on a job in the jobs list
function handleJobClick(event) {
  // Handle delete button click on job list
  const deleteBtn = event.target.closest(".delete-job-btn");
  if (deleteBtn) {
    const jobId = deleteBtn.getAttribute("data-job-id");
    if (jobId) deleteJob(jobId);
    return;
  }
  const jobCard = event.target.closest(".job-card");
  if (jobCard) {
    const jobId = jobCard.getAttribute("data-job-id");
    if (jobId) {
      // Toggle off if already selected
      if (jobCard.classList.contains("selected")) {
        const details = document.getElementById("jobDetails");
        if (details) details.innerHTML = '';
        jobCard.classList.remove("selected");
        return;
      }
      const userId = window.currentUserId;
      showJobDetails(jobId, userId);

      // Update selected state
      document.querySelectorAll(".job-card").forEach(card => {
        card.classList.remove("selected");
      });
      jobCard.classList.add("selected");
    }
  }
}

// Function to handle job actions (like ranking)
function handleJobActions(event) {
  const rankBtn = event.target.closest(".rank-job-btn");
  const deleteBtn = event.target.closest(".delete-job-btn");

  if (rankBtn) {
    const jobId = rankBtn.getAttribute("data-job-id");
    if (jobId) {
      const userId = window.currentUserId;
      rankJob(jobId, userId);
    }
  } else if (deleteBtn) {
    const jobId = deleteBtn.getAttribute("data-job-id");
    if (jobId) {
      deleteJob(jobId);
    }
  }
}

// Function to show job details when a card is clicked
async function showJobDetails(jobId, userId) {
  try {
    console.log(`Showing details for job ${jobId}`);
    const jobDetailsContainer = document.getElementById("jobDetails");

    if (!jobDetailsContainer) {
      console.error("Job details container not found");
      return;
    }

    jobDetailsContainer.innerHTML = '<div class="loading-spinner-container"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div></div>';

    const response = await fetch(`/users/${userId}/jobs/${jobId}`, { headers: { ...window.authHeaders() } });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    const job = await response.json();

    // Format job description with markdown parser if available
    let formattedDescription = job.description || '';
    if (window.marked && formattedDescription) {
      formattedDescription = marked.parse(formattedDescription);
    } else {
      // Basic formatting fallback
      formattedDescription = formattedDescription.replace(/\n/g, '<br>');
    }

    // Create HTML for job details
    let jobHTML = `
      <div class="job-details-header">
        <h2>${job.title || 'Untitled Job'}</h2>
        <div class="job-company-name">${job.company || 'Unknown Company'}</div>
      </div>
      <div class="job-details-content">
        <div class="job-description">${formattedDescription}</div>
      </div>
    `;

    // Add ranking section
    jobHTML += `
      <div class="job-ranking-section mt-4">
        <div class="section-header">
          <h3>Score Breakdown</h3>
        </div>
        <div id="ranking-details-${jobId}" class="content-section">
    `;

    if (job.ranking_score !== null && job.ranking_score !== undefined) {
      // Determine score class
      let scoreClass = 'low';
      if (job.ranking_score >= 8.0) {
        scoreClass = 'high';
      } else if (job.ranking_score >= 5.0) {
        scoreClass = 'medium';
      }

      // Add score display
      jobHTML += `
        <div class="score-display score-${scoreClass}">
          <div class="score-value">${job.ranking_score.toFixed(1)}</div>
          <div class="score-label">Match Score</div>
        </div>
      `;

      // Add explanation if available (fallback to eventData.explanation)
      const explanationText = job.ranking_explanation || job.explanation;
      if (explanationText) {
        let formattedExplanation = explanationText;
        if (window.marked) {
          formattedExplanation = marked.parse(explanationText);
        } else {
          formattedExplanation = explanationText.replace(/\n/g, '<br>');
        }
        jobHTML += `<div class="ranking-explanation-content">${formattedExplanation}</div>`;
      } else {
        jobHTML += `<p><i>Ranking explanation not available.</i></p>`;
      }
    } else {
      // Show loading indicator for ranking
      jobHTML += `
        <div id="ranking-loader-${jobId}" class="loader-container">
          <p><i>Calculating score...</i></p>
          <div class="spinner-border spinner-border-sm text-secondary" role="status">
            <span class="visually-hidden">Loading...</span>
          </div>
        </div>
      `;
    }

    jobHTML += `</div>`; // End ranking-details

    // Add tailoring suggestions section
    jobHTML += `
      <div class="job-tailoring-section mt-4">
        <div class="section-header">
          <h3>Tailoring Suggestions</h3>
        </div>
        <div id="tailoring-suggestions-${jobId}" class="content-section">
    `;
    // Fallback to job.tailoring_suggestions or job.suggestions
    const suggestionsText = job.tailoring_suggestions || job.suggestions;
    if (suggestionsText) {
      let formattedSuggestions = suggestionsText;
      if (window.marked) {
        formattedSuggestions = marked.parse(suggestionsText);
      } else {
        formattedSuggestions = suggestionsText.replace(/\n/g, '<br>');
      }
      jobHTML += `<div class="tailoring-suggestions-content">${formattedSuggestions}</div>`;
    } else {
      // Show loading indicator for tailoring
      jobHTML += `
        <div id="tailoring-loader-${jobId}" class="loader-container">
          <p><i>Generating suggestions...</i></p>
          <div class="spinner-border spinner-border-sm text-secondary" role="status">
            <span class="visually-hidden">Loading...</span>
          </div>
        </div>
      `;
    }

    jobHTML += `</div>`; // End tailoring-suggestions

    // Render HTML
    jobDetailsContainer.innerHTML = jobHTML;
  } catch (error) {
    console.error(`Error showing job details:`, error);
    const jobDetailsContainer = document.getElementById("jobDetails");
    if (jobDetailsContainer) {
      jobDetailsContainer.innerHTML = `<div class="error-message">Error loading job details: ${error.message}</div>`;
    }
  }
}

// --- Delete Job Helpers ---

async function deleteJob(jobId) {
  try {
    const res = await fetch(`/users/${window.currentUserId}/jobs/${jobId}`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        ...window.authHeaders(),
      },
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to delete job');
    }
    removeJobFromList(jobId);
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Deletion error', 'error');   // reuse existing toast fn
  }
}

function removeJobFromList(jobId) {
  const el = document.querySelector(`[data-job-id="${jobId}"]`);
  if (el) el.remove();

  // clear details panel if it was showing this job
  if (window.selectedJobId === jobId) {
    document.getElementById('jobDetails').innerHTML =
      '<p class="placeholder">Select a job to view details...</p>';
    window.selectedJobId = null;
  }

  // Check if there are no more jobs
  const jobsList = document.getElementById("jobsList");
  if (jobsList && !jobsList.querySelector(".job-card")) {
    jobsList.innerHTML = '<p class="placeholder">No jobs saved yet. Add a job using the form above.</p>';
  }
}

// expose for SSE consumer
window.removeJobFromList = removeJobFromList;

// --- Processing Indicator Utility ---
function updateProcessingIndicator(count) {
  const indicator = document.getElementById('savingIndicator');
  const text      = document.getElementById('savingIndicatorText');
  if (!indicator || !text) return;

  if (count > 0) {
    indicator.style.display = 'flex';          // garde le spinner visible
    text.textContent = `Processing ${count} Job${count > 1 ? 's' : ''}`;
    text.dataset.count = count;
  } else {
    indicator.style.display = 'none';
    text.dataset.count = 0;
  }
}
window.updateProcessingIndicator = updateProcessingIndicator;
