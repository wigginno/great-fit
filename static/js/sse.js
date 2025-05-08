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
  if (eventSource) {
    eventSource.close();
  }

  const token = localStorage.getItem('id_token');
  let url = token ? `/stream-jobs?token=${token}` : `/stream-jobs?user_id=${userId || window.currentUserId || ''}`;
  
  eventSource = new EventSource(url);
  console.log("SSE: Connecting to " + url);

  eventSource.onopen = function(event) {
    console.log("SSE: Connection opened.");
  };

  eventSource.onerror = function(event) {
    console.error("SSE: Error", event);
    if (eventSource.readyState === EventSource.CLOSED) {
      console.log("SSE: Connection closed. Attempting to reconnect...");
      setTimeout(() => connectToSSE(userId), 5000);
    }
  };

  eventSource.addEventListener("job_created", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received job_created", eventData);
    if (typeof loadJobs === 'function') loadJobs();
  });

  eventSource.addEventListener("job_deleted", function(event) {
    try {
      const eventData = JSON.parse(event.data);
      console.log("SSE: Received job_deleted", eventData);
      if (eventData.job_id) window.removeJobFromList(eventData.job_id);
    } catch (e) {
      console.error("SSE: Error processing job_deleted event data", e, event.data);
    }
  });

  eventSource.addEventListener("job_ranked", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received job_ranked", eventData);

    // Update job card in the list
    const jobCard = document.querySelector(`.job-card[data-job-id="${eventData.job_id}"]`);
    let scoreText = 'Ranking Failed';
    if (jobCard) {
      const scoreElement = jobCard.querySelector('.job-score-display');
      if (scoreElement) {
        if (eventData.score !== null && eventData.score !== undefined) {
          scoreText = `Match: ${eventData.score.toFixed(1)}/10`;
          scoreElement.textContent = scoreText;
          const clamped = Math.max(0, Math.min(10, eventData.score));
          let bgColor = 'bg-red-500';
          if (clamped >= 7.5) bgColor = 'bg-green-500';
          else if (clamped >= 4.5) bgColor = 'bg-yellow-500';
          scoreElement.classList.remove('bg-gray-400', 'bg-red-500', 'bg-yellow-500', 'bg-green-500');
          scoreElement.classList.add(bgColor);
        } else {
          scoreElement.textContent = scoreText;
          scoreElement.classList.remove('bg-gray-400', 'bg-yellow-500', 'bg-green-500');
          scoreElement.classList.add('bg-red-500');
        }
      }
    }

    // Update job details view if it's the currently selected job
    if (String(window.selectedJobId) === String(eventData.job_id)) {
      const rankingDetailsContainer = document.getElementById(`ranking-details-${eventData.job_id}`);
      if (rankingDetailsContainer) {
        const loader = document.getElementById(`ranking-loader-${eventData.job_id}`);
        if(loader) loader.style.display = 'none';

        let newScoreHtml = '';
        if (eventData.score !== null && eventData.score !== undefined) {
            const clampedScore = Math.max(0, Math.min(10, eventData.score));
            let scoreColorClass = 'text-red-700';
            if (clampedScore >= 7.5) scoreColorClass = 'text-green-700';
            else if (clampedScore >= 4.5) scoreColorClass = 'text-yellow-700';
            newScoreHtml = `
                <div class="flex items-baseline">
                    <span class="text-3xl font-bold ${scoreColorClass}">${eventData.score.toFixed(1)}</span>
                    <span class="text-sm text-gray-500 ml-1">/ 10 Match Score</span>
                </div>`;
        } else {
            newScoreHtml = `<p class="text-red-600 font-medium">Ranking failed or score not available.</p>`;
        }
        
        // Update score display (first child of rankingDetailsContainer or specific element)
        const scoreDisplayElement = rankingDetailsContainer.querySelector('.flex.items-baseline') || rankingDetailsContainer.firstChild;
        if(scoreDisplayElement && scoreDisplayElement.parentNode === rankingDetailsContainer) { // ensure it's a direct child or the one we target
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = newScoreHtml;
            rankingDetailsContainer.replaceChild(tempDiv.firstChild, scoreDisplayElement);
        } else { // fallback to just prepending
            rankingDetailsContainer.insertAdjacentHTML('afterbegin', newScoreHtml);
        }

        const explanationContent = rankingDetailsContainer.querySelector('.ranking-explanation-content');
        if (explanationContent) {
          const explanationHtml = eventData.explanation ? (window.marked ? marked.parse(eventData.explanation) : `<div class="prose prose-sm max-w-none whitespace-pre-wrap">${eventData.explanation.replace(/\n/g, '<br>')}</div>`) : '<p class="text-sm text-gray-500 italic">Ranking explanation not available.</p>';
          explanationContent.innerHTML = explanationHtml;
        }
      }
    }
    showToast(`Job ${eventData.job_id} ranked: ${scoreText}`, 'info');
  });

  eventSource.addEventListener("job_tailored", function(event) {
    const eventData = JSON.parse(event.data);
    console.log("SSE: Received job_tailored", eventData);
    if (String(window.selectedJobId) === String(eventData.job_id)) {
      const tailoringDetailsContainer = document.getElementById(`tailoring-suggestions-${eventData.job_id}`);
      if (tailoringDetailsContainer) {
        const loader = document.getElementById(`tailoring-loader-${eventData.job_id}`);
        if(loader) loader.style.display = 'none';
        
        const suggestionsContent = tailoringDetailsContainer.querySelector('.tailoring-suggestions-content');
        if (suggestionsContent) {
          const suggestionsHtml = eventData.suggestions ? (window.marked ? marked.parse(eventData.suggestions) : `<div class="prose prose-sm max-w-none whitespace-pre-wrap">${eventData.suggestions.replace(/\n/g, '<br>')}</div>`) : '<p class="text-sm text-gray-500 italic">Tailoring suggestions not available.</p>';
          suggestionsContent.innerHTML = suggestionsHtml;
        }
      }
    }
  });

  eventSource.addEventListener("job_error", function(event) {
    const eventData = JSON.parse(event.data);
    console.error("SSE: Received job_error", eventData);
    showToast(`Error processing job ${eventData.job_id}: ${eventData.message}`, 'error');
  });

  eventSource.addEventListener("processing_count_update", function (event) {
    const data = JSON.parse(event.data);
    console.log("SSE: Received processing_count_update", data);
    if (typeof window.updateProcessingIndicator === 'function') {
      window.updateProcessingIndicator(data.count);
    }
  });
}
