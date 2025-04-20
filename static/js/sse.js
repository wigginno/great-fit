/**
 * sse.js - Server-Sent Events handling
 * Manages the real-time connection with the server to receive updates
 */

// Global SSE connection
let eventSource = null;

// Function to connect to SSE for real-time updates
function connectToSSE(userId) {
  // Close any existing connection
  if (eventSource) {
    eventSource.close();
  }

  // Create new connection
  eventSource = new EventSource(`/stream-jobs/${userId}`);
  console.log("SSE: Connecting to /stream-jobs/" + userId);

  // Connection events
  eventSource.onopen = function(event) {
    console.log("SSE: Connection opened.");
  };

  eventSource.onerror = function(event) {
    console.error("SSE: Error", event);
    if (eventSource.readyState === EventSource.CLOSED) {
      console.log("SSE: Connection closed. Attempting to reconnect...");
      // Try to reconnect after a delay
      setTimeout(() => connectToSSE(userId), 5000);
    }
  };

  // Handle job_created events
  eventSource.addEventListener("job_created", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received job_created", eventData);
    
    // Add the new job to the list
    addJobCardToList(eventData, true);
  });

  // Handle job_deleted events
  eventSource.addEventListener("job_deleted", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received job_deleted", eventData);
    
    // Remove the job card
    const jobCard = document.querySelector(`.job-card[data-job-id="${eventData.job_id}"]`);
    if (jobCard) {
      jobCard.remove();
    }
    
    // Clear details if the deleted job was being viewed
    const jobDetails = document.getElementById("jobDetails");
    const currentJobId = jobDetails.getAttribute("data-job-id");
    if (currentJobId == eventData.job_id) {
      jobDetails.innerHTML = '<p class="placeholder">Select a job to view details</p>';
      jobDetails.removeAttribute("data-job-id");
    }
    
    showToast(`Job ${eventData.job_id} was deleted`, "info");
  });

  // Handle job_ranked events
  eventSource.addEventListener("job_ranked", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received job_ranked", eventData);
    // Persist ranking explanation and score for reload
    if (eventData.explanation !== undefined) {
      localStorage.setItem(`job_ranked_explanation_${eventData.job_id}`, eventData.explanation);
    }
    if (eventData.score !== undefined) {
      localStorage.setItem(`job_ranked_score_${eventData.job_id}`, eventData.score);
    }
    // Update card if present
    const jobCard = document.querySelector(`.job-card[data-job-id="${eventData.job_id}"]`);
    if (jobCard) {
      // Define scoreText variable at this scope level so it's available for the toast
      let scoreText = 'Scoring job...';
      
      // Update score display
      const scoreElement = jobCard.querySelector('.job-score');
      if (scoreElement) {
        let scoreClass = 'unranked';
        let scoreColor = '#6c757d';
        const score = eventData.score;

        if (score !== null && score !== undefined) {
          scoreText = score.toFixed(1);
          if (score >= 8.0) {
            scoreClass = 'high'; scoreColor = '#198754';
          } else if (score >= 5.0) {
            scoreClass = 'medium'; scoreColor = '#ffc107';
          } else {
            scoreClass = 'low'; scoreColor = '#dc3545';
          }
        } else {
           scoreText = 'Rank Failed'; scoreClass = 'low'; scoreColor = '#dc3545';
        }
        scoreElement.textContent = scoreText;
        scoreElement.className = `job-score score-${scoreClass}`; // Update class
        scoreElement.style.backgroundColor = scoreColor;
        scoreElement.style.color = 'white';
        scoreElement.style.padding = '0.2rem 0.5rem';
        scoreElement.style.borderRadius = '0.25rem';
      }

      // Update ranking details section
      const rankingDetailsContainer = document.getElementById(`ranking-details-${eventData.job_id}`);
      const rankingLoader = document.getElementById(`ranking-loader-${eventData.job_id}`);
      if (rankingDetailsContainer) {
        if (rankingLoader) rankingLoader.style.display = 'none';
        const explanationHtml = eventData.explanation ? marked.parse(eventData.explanation) : '<p><i>Ranking explanation not available.</i></p>';
        // Ensure content div exists or create it
        let contentDiv = rankingDetailsContainer.querySelector('.ranking-explanation-content');
        if (!contentDiv) {
          contentDiv = document.createElement('div');
          contentDiv.className = 'ranking-explanation-content';
          rankingDetailsContainer.appendChild(contentDiv);
        }
        contentDiv.innerHTML = explanationHtml;
      }
      showToast(`Job ${eventData.job_id} ranked: ${scoreText}`, 'info');
    }
  });

  // Handle tailoring suggestions generated
  eventSource.addEventListener("job_tailored", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received job_tailored", eventData);
    // Persist tailoring suggestions for reload
    if (eventData.suggestions !== undefined) {
      localStorage.setItem(`job_tailored_suggestions_${eventData.job_id}`, eventData.suggestions);
    }
    // Update details container if present
    const tailoringDetailsContainer = document.getElementById(`tailoring-suggestions-${eventData.job_id}`);
    if (tailoringDetailsContainer) {
      const tailoringLoader = document.getElementById(`tailoring-loader-${eventData.job_id}`);
      if (tailoringLoader) tailoringLoader.style.display = 'none';
      const suggestionsHtml = eventData.suggestions ? marked.parse(eventData.suggestions) : '<p><i>Tailoring suggestions not available.</i></p>';
      // Ensure content div exists or create it
      let contentDiv = tailoringDetailsContainer.querySelector('.tailoring-suggestions-content');
      if (!contentDiv) {
        contentDiv = document.createElement('div');
        contentDiv.className = 'tailoring-suggestions-content';
        tailoringDetailsContainer.appendChild(contentDiv);
      }
      contentDiv.innerHTML = suggestionsHtml;
    }
  });

  // Handle job processing errors
  eventSource.addEventListener("job_error", function(event) {
    const eventData = JSON.parse(event.data);
    console.error("SSE: Received job_error", eventData);
    showToast(`Error processing job ${eventData.job_id}: ${eventData.message}`, 'error');
  });

  // Handle job processing count updates
  eventSource.addEventListener("processing_count_update", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received processing_count_update", eventData);
    // Update UI if needed to show processing status
    const processingCountIndicator = document.getElementById("processingCountIndicator");
    if (processingCountIndicator) {
      if (eventData.count > 0) {
        processingCountIndicator.style.display = "inline-block";
        processingCountIndicator.textContent = eventData.count;
      } else {
        processingCountIndicator.style.display = "none";
      }
    }
  });
}

// Helper function to add a new job card to the list
function addJobCardToList(job, prepend = false) {
  const jobsContainer = document.getElementById("jobsList");
  if (!jobsContainer) return;
  
  // If currently showing placeholder, clear it
  if (jobsContainer.querySelector('.placeholder')) {
    jobsContainer.innerHTML = '<div class="jobs-list"></div>';
  }
  
  const jobsList = jobsContainer.querySelector('.jobs-list');
  if (!jobsList) return;
  
  // Create card element
  const jobCard = document.createElement('div');
  jobCard.className = 'job-card';
  jobCard.setAttribute('data-job-id', job.id);
  jobCard.id = `job-card-${job.id}`;
  
  // Structure matches the createJobCardHtml function
  jobCard.innerHTML = `
    <div class="job-title">${job.title || "Untitled Job"}</div>
    <div class="job-company">${job.company || "Unknown Company"}</div>
    ${
      job.ranking_score !== null && job.ranking_score !== undefined
        ? `<div class="job-score">Match: ${job.ranking_score.toFixed(1)}/10</div>`
        : '<div class="job-score unranked">Scoring job...</div>'
    }
  `;
  
  // Add to the beginning or end of the list
  if (prepend) {
    jobsList.insertBefore(jobCard, jobsList.firstChild);
  } else {
    jobsList.appendChild(jobCard);
  }
  
  // Style the score element
  const scoreElement = jobCard.querySelector('.job-score');
  if (scoreElement) {
    if (job.ranking_score !== null && job.ranking_score !== undefined) {
      // Map score 0-10 to hue 0-120 (Red to Green)
      const score = Math.max(0, Math.min(10, job.ranking_score)); // Clamp score
      const hue = (score / 10) * 120;
      scoreElement.style.backgroundColor = `hsl(${hue}, 90%, 45%)`;
    } else {
      scoreElement.style.backgroundColor = '#6c757d'; // Grey for unranked
    }
    scoreElement.style.color = 'white';
    scoreElement.style.padding = '0.1rem 0.4rem';
    scoreElement.style.borderRadius = '0.25rem';
    scoreElement.style.display = 'inline-block';
  }
  
  // Show toast notification
  showToast(`New job added: ${job.title || "Untitled Job"}`);
}
