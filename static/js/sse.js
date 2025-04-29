/**
 * sse.js - Server-Sent Events handling
 * Manages the real-time connection with the server to receive updates
 */

// Global SSE connection
let eventSource = null;

// Wait for currentUserId to be set then connect automatically
document.addEventListener('DOMContentLoaded', () => {
  const maybeConnect = () => {
    if (window.currentUserId) {
      connectToSSE(window.currentUserId);
    } else {
      setTimeout(maybeConnect, 500);
    }
  };
  maybeConnect();
});

// Function to connect to SSE for real-time updates
function connectToSSE(userId = window.currentUserId) {
  // Close any existing connection
  if (eventSource) {
    eventSource.close();
  }

  // Create new connection
  // For SSE, token cannot be sent via headers easily, so include token as query param
  const token = localStorage.getItem('id_token');
  let url;
  if (token) {
    url = `/stream-jobs?token=${token}`;
  } else {
    // Local dev: include user_id query param so backend authorizes connection
    const id = userId || window.currentUserId;
    url = id ? `/stream-jobs?user_id=${id}` : `/stream-jobs`;
  }
  eventSource = new EventSource(url);
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
    // Re-render job list for consistent styling
    if (typeof loadJobs === 'function') {
      loadJobs();
    }
  });

  // Handle job_deleted events
  eventSource.addEventListener("job_deleted", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received job_deleted", eventData);

    if (eventData.job_id) window.removeJobFromList(eventData.job_id);

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
        if (eventData.score !== null && eventData.score !== undefined) {
          scoreText = eventData.score.toFixed(1);
          const clamped = Math.max(0, Math.min(10, eventData.score));
          const hue = (clamped / 10) * 120;
          scoreElement.style.backgroundColor = `hsl(${hue}, 90%, 45%)`;
        } else {
          scoreText = 'Rank Failed';
          scoreElement.style.backgroundColor = `hsl(0, 90%, 45%)`;
        }
        scoreElement.textContent = scoreText;
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
    // No client persistence; always rely on server data
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
  eventSource.addEventListener("processing_count_update", function (event) {
    const data = JSON.parse(event.data);
    console.log("SSE: Received processing_count_update", data);
    if (typeof window.updateProcessingIndicator === 'function') {
      window.updateProcessingIndicator(data.count);
    }
  });
}

// addJobCardToList removed – list is always refreshed via loadJobs()
