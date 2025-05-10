/**
 * jobs.js - Job management functionality
 * Handles loading, displaying, and managing job listings
 */

// Function to load and display jobs
async function loadJobs() {
  try {
    const userId = window.currentUserId;
    const jobsContainer = document.getElementById("jobsList");
    jobsContainer.innerHTML = '<p class="text-gray-500 italic">Loading jobs...</p>';

    const response = await fetch(`/jobs/`, { headers: await window.authHeaders() });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        console.error(`Authentication error (${response.status}) accessing /jobs/. Redirecting to login.`);
        showToast("Your session may have expired. Please sign in again.", "error");
        window.dispatchEvent(new CustomEvent('logoutSuccess'));
        Auth.federatedSignIn();
        return;
      }
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    const jobs = await response.json();

    let processingCount = 0;
    if (jobs && Array.isArray(jobs)) { // Ensure jobs is an array
      jobs.forEach(job => {
        if (job.ranking_score === null || job.ranking_score === undefined) {
          processingCount++;
        }
      });
    }
    window.updateProcessingIndicator(processingCount);

    if (jobs.length === 0) {
      jobsContainer.innerHTML = '<p class="text-gray-500 italic">No jobs saved yet. Click "Add Job" to get started.</p>';
      return;
    }

    let jobsHtml = '<div class="space-y-3">';

    jobs.forEach((job) => {
      const scoreDisplay = job.ranking_score !== null && job.ranking_score !== undefined
        ? `<div class="job-score-display mt-1 inline-block rounded-full px-3 py-1 text-xs font-semibold text-white">Match: ${job.ranking_score.toFixed(1)}/10</div>`
        : '<div class="job-score-display mt-1 inline-block rounded-full bg-gray-400 px-3 py-1 text-xs font-semibold text-white">Processing...</div>';

      jobsHtml += `
        <div class="job-card relative rounded-lg bg-white border border-gray-200 p-4 hover:shadow-lg transition-shadow duration-200 cursor-pointer" data-job-id="${job.id}">
          <button class="delete-job-btn absolute top-2 right-2 p-1 text-gray-400 hover:text-red-500 transition-colors" data-job-id="${job.id}" title="Delete Job">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 16 16" class="w-5 h-5">
              <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0z"/>
              <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
            </svg>
          </button>
          <div class="font-semibold text-gray-800 truncate pr-8" title="${job.title || "Untitled Job"}">${job.title || "Untitled Job"}</div>
          <div class="text-sm text-gray-500 truncate pr-8" title="${job.company || "Unknown Company"}">${job.company || "Unknown Company"}</div>
          ${scoreDisplay}
        </div>
      `;
    });

    jobsHtml += "</div>";
    jobsContainer.innerHTML = jobsHtml;

    jobsContainer.querySelectorAll(".job-card").forEach((card) => {
      const jobId = card.getAttribute("data-job-id");
      const job = jobs.find((j) => String(j.id) === jobId);
      if (job) {
        const scoreElement = card.querySelector(".job-score-display");
        if (scoreElement && job.ranking_score !== null && job.ranking_score !== undefined) {
          const clamped = Math.max(0, Math.min(10, job.ranking_score));
          let bgColor = 'bg-red-500'; // Low score
          if (clamped >= 7.5) bgColor = 'bg-green-500'; // High score
          else if (clamped >= 4.5) bgColor = 'bg-yellow-500'; // Medium score
          scoreElement.classList.remove('bg-gray-400'); // Remove default processing color
          scoreElement.classList.add(bgColor);
        }
      }
    });

  } catch (error) {
    console.error("Error loading jobs:", error);
    const jobsContainer = document.getElementById("jobsList");
    jobsContainer.innerHTML = `<p class="text-red-600 font-medium">Error loading jobs: ${error.message}</p>`;
  }
}

// Function to save job from modal
async function saveModalJob() {
  const rawJobDescription = document.getElementById("rawJobDescription");
  const modalErrorDiv = document.getElementById("modal-error");

  if (!rawJobDescription.value.trim()) {
    modalErrorDiv.textContent = "Job description is required.";
    rawJobDescription.focus();
    return;
  }

  const payload = { content: rawJobDescription.value };
  showToast("Job submitted - processing in background...", "success");
  window.dispatchEvent(new CustomEvent('close-add-job-modal'));
  await fetch(`/jobs/markdown`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await window.authHeaders()) },
    body: JSON.stringify(payload),
  });
  await loadJobs();
}

// Function to handle clicking on a job in the jobs list
function handleJobClick(event) {
  const deleteBtn = event.target.closest(".delete-job-btn");
  if (deleteBtn) {
    event.stopPropagation();
    const jobId = deleteBtn.getAttribute("data-job-id");
    if (jobId) deleteJobWithConfirmation(jobId);
    return;
  }

  const jobCard = event.target.closest(".job-card");
  if (jobCard) {
    const jobId = jobCard.getAttribute("data-job-id");
    if (jobId) {
      if (jobCard.classList.contains("ring-2")) { // Check for selection style
        const details = document.getElementById("jobDetails");
        if (details) details.innerHTML = '<p class="text-gray-500 italic">Select a job to see details.</p>';
        jobCard.classList.remove("ring-2", "ring-indigo-500", "bg-indigo-50");
        window.selectedJobId = null;
        return;
      }
      showJobDetails(jobId, window.currentUserId);
      document.querySelectorAll(".job-card.ring-2").forEach(card => {
        card.classList.remove("ring-2", "ring-indigo-500", "bg-indigo-50");
      });
      jobCard.classList.add("ring-2", "ring-indigo-500", "bg-indigo-50");
      window.selectedJobId = jobId;
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

    jobDetailsContainer.innerHTML = `
      <div class="flex justify-center items-center h-full">
        <svg class="animate-spin h-8 w-8 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="ml-2 text-gray-500">Loading details...</span>
      </div>`;

    const response = await fetch(`/jobs/${jobId}`, { headers: await window.authHeaders() });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        showToast("Your session may have expired. Please sign in again.", "error");
        window.dispatchEvent(new CustomEvent('logoutSuccess')); Auth.federatedSignIn(); return;
      }
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    const job = await response.json();
    let formattedDescription = job.description || '';
    if (window.marked && formattedDescription) {
      formattedDescription = marked.parse(formattedDescription);
    } else {
      formattedDescription = `<p class="whitespace-pre-wrap">${formattedDescription.replace(/\n/g, '<br>')}</p>`;
    }

    let scoreHtml = `
      <div id="ranking-loader-${jobId}" class="flex items-center text-sm text-gray-500">
        <svg class="animate-spin h-5 w-5 mr-2 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <i>Calculating score...</i>
      </div>`;
    let explanationHtml = `<p class="text-sm text-gray-500 italic">Ranking explanation will appear here once processed.</p>`;

    if (job.ranking_score !== null && job.ranking_score !== undefined) {
      const clampedScore = Math.max(0, Math.min(10, job.ranking_score));
      let scoreColor = 'bg-red-100 text-red-700';
      if (clampedScore >= 7.5) scoreColor = 'bg-green-100 text-green-700';
      else if (clampedScore >= 4.5) scoreColor = 'bg-yellow-100 text-yellow-700';
      
      scoreHtml = `
        <div class="flex items-baseline">
          <span class="text-3xl font-bold ${scoreColor.split(' ')[1]}">${job.ranking_score.toFixed(1)}</span>
          <span class="text-sm text-gray-500 ml-1">/ 10 Match Score</span>
        </div>
      `;
      const explanationText = job.ranking_explanation || job.explanation; // Fallback
      if (explanationText) {
        explanationHtml = window.marked ? marked.parse(explanationText) : `<div class="prose prose-sm max-w-none whitespace-pre-wrap">${explanationText.replace(/\n/g, '<br>')}</div>`;
      } else {
        explanationHtml = `<p class="text-sm text-gray-500 italic">Ranking explanation not available.</p>`;
      }
    }

    let suggestionsHtml = `
      <div id="tailoring-loader-${jobId}" class="flex items-center text-sm text-gray-500">
        <svg class="animate-spin h-5 w-5 mr-2 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <i>Generating suggestions...</i>
      </div>`;
    const suggestionsText = job.tailoring_suggestions || job.suggestions; // Fallback
    if (suggestionsText) {
      suggestionsHtml = window.marked ? marked.parse(suggestionsText) : `<div class="prose prose-sm max-w-none whitespace-pre-wrap">${suggestionsText.replace(/\n/g, '<br>')}</div>`;
    }

    const jobHTML = `
      <div class="space-y-6">
        <div>
          <h2 class="text-2xl font-bold text-gray-800">${job.title || 'Untitled Job'}</h2>
          <p class="text-md text-gray-600">${job.company || 'Unknown Company'}</p>
        </div>
        <div class="prose prose-sm max-w-none text-gray-700">${formattedDescription}</div>
        
        <div class="border-t border-gray-200 pt-4">
          <h3 class="text-lg font-semibold text-gray-800 mb-2">Score Breakdown</h3>
          <div id="ranking-details-${jobId}" class="p-4 bg-white rounded-md shadow-sm ring-1 ring-gray-200">
            ${scoreHtml}
            <div class="mt-3 ranking-explanation-content prose prose-sm max-w-none">${explanationHtml}</div>
          </div>
        </div>

        <div class="border-t border-gray-200 pt-4">
          <h3 class="text-lg font-semibold text-gray-800 mb-2">Tailoring Suggestions</h3>
          <div id="tailoring-suggestions-${jobId}" class="p-4 bg-white rounded-md shadow-sm ring-1 ring-gray-200">
            <div class="tailoring-suggestions-content prose prose-sm max-w-none">${suggestionsHtml}</div>
          </div>
        </div>
      </div>
    `;
    jobDetailsContainer.innerHTML = jobHTML;

  } catch (error) {
    console.error(`Error showing job details:`, error);
    const jobDetailsContainer = document.getElementById("jobDetails");
    if (jobDetailsContainer) {
      jobDetailsContainer.innerHTML = `<div class="p-4 text-red-600 bg-red-50 rounded-md">Error loading job details: ${error.message}</div>`;
    }
  }
}

// --- Delete Job Helpers ---
function deleteJobWithConfirmation(jobId) {
  if (window.confirm("Are you sure you want to delete this job? This action cannot be undone.")) {
    actualDeleteJob(jobId);
  }
}

async function actualDeleteJob(jobId) {
  const jobCardElement = document.querySelector(`.job-card[data-job-id="${jobId}"]`);
  if (jobCardElement) jobCardElement.style.opacity = "0.5";

  try {
    const res = await fetch(`/jobs/${jobId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", ...(await window.authHeaders()) },
    });
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) {
        showToast("Your session may have expired. Please sign in again.", "error");
        window.dispatchEvent(new CustomEvent('logoutSuccess')); Auth.federatedSignIn();
        throw new Error(`Authentication error: ${res.status}`);
      }
      const errData = await res.json().catch(() => ({ detail: 'Failed to delete job and parse error response.' }));
      throw new Error(errData.detail || 'Failed to delete job');
    }

    const result = await res.json();
    showToast(`Job "${result.job_id}" deleted successfully.`, 'success');
    // UI update will be handled by SSE or direct call to removeJobFromList if SSE is not immediate enough
    // For immediate feedback if SSE is slow:
    removeJobFromList(jobId);

  } catch (err) {
    console.error('Error during job deletion:', err);
    showToast(err.message || 'Deletion error. Please try again.', 'error');
    if (jobCardElement) jobCardElement.style.opacity = "1";
  }
}

function removeJobFromList(jobId) {
  const el = document.querySelector(`.job-card[data-job-id="${jobId}"]`);
  if (el) el.remove();

  const jobDetailsContainer = document.getElementById("jobDetails");
  if (String(window.selectedJobId) === String(jobId)) {
    if (jobDetailsContainer) jobDetailsContainer.innerHTML = '<p class="text-gray-500 italic">Select a job to see details.</p>';
    window.selectedJobId = null;
  }

  const jobsList = document.getElementById("jobsList");
  if (jobsList && !jobsList.querySelector(".job-card")) {
    jobsList.innerHTML = '<p class="text-gray-500 italic">No jobs saved yet. Click "Add Job" to get started.</p>';
  }
}

window.removeJobFromList = removeJobFromList;
window.loadJobs = loadJobs;

// --- Processing Indicator Utility ---
function updateProcessingIndicator(count) {
  const indicator = document.getElementById('savingIndicator');
  const textEl = document.getElementById('savingIndicatorText'); // Renamed for clarity
  if (!indicator || !textEl) return;

  if (count > 0) {
    indicator.classList.remove('hidden');
    indicator.classList.add('flex'); // Ensure it's flex if hidden was by display:none
    textEl.textContent = `Processing ${count} Job${count > 1 ? 's' : ''}...`;
    textEl.dataset.count = count;
  } else {
    indicator.classList.add('hidden');
    indicator.classList.remove('flex');
    textEl.dataset.count = 0;
  }
}
window.updateProcessingIndicator = updateProcessingIndicator;
