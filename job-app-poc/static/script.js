// --- Core Functions --- //

// Function to save a job description
async function saveJob() {
    const jobDescription = document.getElementById('jobDescription').value;
    if (!jobDescription.trim()) {
        alert('Please enter a job description first');
        return;
    }

    try {
        // Call the new backend endpoint that parses the description
        const response = await fetch(`/jobs/parse-and-save/`, { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            // Send only the raw description text
            body: JSON.stringify({ description_text: jobDescription }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const savedJob = await response.json();
        alert('Job saved successfully!');
        
        // Optionally refresh the jobs list
        loadJobs();
    } catch (error) {
        console.error('Error saving job:', error);
        alert(`Failed to save job: ${error.message}`);
    }
}

// Function to load and display user profile
async function loadProfile() {
    try {
        // For now, hardcode user ID to 1
        const userId = 1;
        const profileContainer = document.getElementById('userProfile');
        profileContainer.innerHTML = 'Loading profile...';

        const response = await fetch(`/users/${userId}/profile`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const profile = await response.json();
        
        profileContainer.innerHTML = `
            <h3>${profile.user_id ? 'User ' + profile.user_id : 'Profile'}</h3>
            <pre>${profile.content}</pre>
        `;
        
        // Optionally store the user ID in a data attribute for later use
        profileContainer.setAttribute('data-user-id', profile.user_id);
        
    } catch (error) {
        console.error('Error loading profile:', error);
        document.getElementById('userProfile').innerHTML = 
            `<p style="color: red;">Error loading profile: ${error.message}</p>`;
    }
}

// Function to load and display all saved jobs
async function loadJobs() {
    try {
        // For now, hardcode user ID to 1
        const userId = 1;
        const jobsListContainer = document.getElementById('jobsList');
        jobsListContainer.innerHTML = 'Loading jobs...';

        const response = await fetch(`/users/${userId}/jobs`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const jobs = await response.json();
        
        if (jobs.length === 0) {
            jobsListContainer.innerHTML = '<p>No jobs found. Save a job description to get started.</p>';
            return;
        }
        
        // Create a list of jobs
        let jobsList = '<ul class="jobs-list">';
        jobs.forEach(job => {
            const scoreClass = job.ranking_score ? 
                (job.ranking_score >= 7 ? 'high-match' : 
                 job.ranking_score >= 5 ? 'medium-match' : 'low-match') : '';
                 
            jobsList += `
                <li class="job-item ${scoreClass}" data-job-id="${job.id}">
                    <span class="job-title">${job.title || 'Untitled Job'}</span>
                    ${job.ranking_score ? `<span class="job-score">Score: ${job.ranking_score}</span>` : ''}
                </li>
            `;
        });
        jobsList += '</ul>';
        
        jobsListContainer.innerHTML = jobsList;
        
        // Add click event listeners to job items
        document.querySelectorAll('.job-item').forEach(jobItem => {
            jobItem.addEventListener('click', async () => {
                const jobId = jobItem.getAttribute('data-job-id');
                await showJobDetails(jobId, userId);
                
                document.querySelectorAll('.job-item').forEach(item => {
                    item.classList.remove('active');
                });
                jobItem.classList.add('active');
            });
        });
        
    } catch (error) {
        console.error('Error loading jobs:', error);
        document.getElementById('jobsList').innerHTML = 
            `<p style="color: red;">Error loading jobs: ${error.message}</p>`;
    }
}

// Function to show job details and add ranking functionality
async function showJobDetails(jobId, userId) {
    try {
        const jobDetailsContainer = document.getElementById('jobDetails');
        jobDetailsContainer.innerHTML = 'Loading job details...';

        const response = await fetch(`/users/${userId}/jobs/${jobId}`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const job = await response.json();
        
        let jobDetailsHTML = `
            <h3>${job.title || 'Job Details'}</h3>
            <div class="job-description">
                <h4>Description:</h4>
                <pre>${job.description}</pre>
            </div>
        `;
        
        if (job.ranking_score) {
            jobDetailsHTML += `
                <div class="job-ranking">
                    <h4>Match Score: ${job.ranking_score}/10</h4>
                    <p>${job.ranking_explanation || ''}</p>
                </div>
            `;
        }
        
        jobDetailsHTML += `
            <button id="rankJobButton" class="btn" data-job-id="${job.id}">
                ${job.ranking_score ? 'Re-rank Job' : 'Rank Job'}
            </button>
        `;
        
        jobDetailsContainer.innerHTML = jobDetailsHTML;
        
        document.getElementById('rankJobButton').addEventListener('click', async () => {
            await rankJob(job.id, userId);
        });
        
    } catch (error) {
        console.error('Error showing job details:', error);
        document.getElementById('jobDetails').innerHTML = 
            `<p style="color: red;">Error loading job details: ${error.message}</p>`;
    }
}

// Function to rank a job against the user profile
async function rankJob(jobId, userId) {
    try {
        const rankButton = document.getElementById('rankJobButton');
        const jobDetailsContainer = document.getElementById('jobDetails');
        
        rankButton.disabled = true;
        rankButton.textContent = 'Ranking...';
        
        jobDetailsContainer.innerHTML += '<p id="ranking-status">Ranking job against your profile. This may take a moment...</p>';
        
        // Correct the endpoint URL
        const response = await fetch(`/jobs/${jobId}/rank`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        
        await showJobDetails(jobId, userId);
        
        await loadJobs();
        
    } catch (error) {
        console.error('Error ranking job:', error);
        document.getElementById('ranking-status').innerHTML = 
            `<p style="color: red;">Error ranking job: ${error.message}</p>`;
        
        const rankButton = document.getElementById('rankJobButton');
        if (rankButton) {
            rankButton.disabled = false;
            rankButton.textContent = 'Try Ranking Again';
        }
    }
}

// --- Tailoring Suggestions --- //

// Function to fetch tailoring suggestions
async function fetchTailoringSuggestions() {
    const jobDescription = document.getElementById('jobDescription').value;
    const userProfileElement = document.getElementById('userProfile');
    const userProfileText = userProfileElement ? userProfileElement.textContent || userProfileElement.innerText : ''; 
    const suggestionsContainer = document.getElementById('tailoringSuggestions');
    suggestionsContainer.innerHTML = 'Loading tailoring suggestions...'; 

    if (!jobDescription) {
        suggestionsContainer.innerHTML = '<p style="color: red;">Please enter a job description first.</p>';
        return;
    }

    const userId = 1; 

    if (!userId) {
         suggestionsContainer.innerHTML = '<p style="color: red;">Please load a user profile first.</p>';
         return;
    }


    try {
        // Correct the endpoint URL to match the backend
        const response = await fetch(`/users/${userId}/jobs/tailor-suggestions`, { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ job_description: jobDescription }), 
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        suggestionsContainer.innerHTML = `<h3>Tailoring Suggestions:</h3><p>${data.suggestions.replace(/\n/g, '<br>')}</p>`;

    } catch (error) {
        console.error('Error fetching tailoring suggestions:', error);
        suggestionsContainer.innerHTML = `<p style="color: red;">Error fetching suggestions: ${error.message}</p>`;
    }
}

// Add event listeners when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const saveJobButton = document.getElementById('saveJobButton');
    const loadProfileButton = document.getElementById('loadProfileButton');
    const loadJobsButton = document.getElementById('loadJobsButton');
    const tailorButton = document.getElementById('tailorButton'); 

    if (saveJobButton) {
        saveJobButton.addEventListener('click', saveJob);
    } else {
        console.warn('Save Job button (id="saveJobButton") not found.');
    }

    if (loadProfileButton) {
        loadProfileButton.addEventListener('click', loadProfile);
    } else {
        console.warn('Load Profile button (id="loadProfileButton") not found.');
    }

    if (loadJobsButton) {
        loadJobsButton.addEventListener('click', loadJobs);
    } else {
        console.warn('Load Jobs button (id="loadJobsButton") not found.');
    }

    if (tailorButton) {
        tailorButton.addEventListener('click', fetchTailoringSuggestions);
    } else {
        console.warn('Tailor button (id="tailorButton") not found.');
    }

    // Initial load (optional)
    // loadProfile();
    // loadJobs();
});
