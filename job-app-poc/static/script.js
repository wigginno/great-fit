document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadProfile();
    loadJobs();

    // Set up event listeners for form submissions
    setupEventListeners();
});

// Set up all event listeners
function setupEventListeners() {
    // Resume upload form
    const resumeUploadForm = document.getElementById('resumeUploadForm');
    if (resumeUploadForm) {
        resumeUploadForm.addEventListener('submit', handleResumeUpload);
    }

    // Save job button
    const saveJobButton = document.getElementById('saveJobButton');
    if (saveJobButton) {
        saveJobButton.addEventListener('click', saveJob);
    }

    // Job list container for job clicking
    const jobsList = document.getElementById('jobsList');
    if (jobsList) {
        jobsList.addEventListener('click', handleJobClick);
    }

    // Job details container for ranking
    const jobDetails = document.getElementById('jobDetails');
    if (jobDetails) {
        jobDetails.addEventListener('click', handleJobActions);
    }

    // Tailoring suggestions button
    const tailorButton = document.getElementById('tailorButton');
    if (tailorButton) {
        tailorButton.addEventListener('click', getTailoringSuggestions);
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

        // Handle 204 No Content status - which means no user or no profile
        if (response.status === 204) {
            const profileStatus = response.headers.get('X-Profile-Status');

            if (profileStatus === 'no_user_found' || profileStatus === 'no_profile_found') {
                // Display a friendly message to create a profile
                profileContainer.innerHTML = `
                    <div class="alert alert-info">
                        <h4><i class="bi bi-info-circle me-2"></i>No Profile Found</h4>
                        <p>Upload your resume to automatically create your profile!</p>
                        <p>You can add your resume using the upload form above.</p>
                    </div>
                `;
                return;
            }
        }

        // Handle other non-200 responses
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const profile = await response.json();

        // Use the formatProfileData function from profileFormatter.js to format the profile
        const formattedProfile = formatProfileData(profile.profile_data);
        profileContainer.innerHTML = formattedProfile;
    } catch (error) {
        console.error('Error loading profile:', error);
        document.getElementById('userProfile').innerHTML = `
            <div class="alert alert-danger">
                <h4><i class="bi bi-exclamation-triangle-fill me-2"></i>Error Loading Profile</h4>
                <p>${error.message}</p>
            </div>
        `;
    }
}

// Function to handle resume upload
async function handleResumeUpload(event) {
    event.preventDefault();

    const uploadStatus = document.getElementById('uploadStatus');
    uploadStatus.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div> Uploading resume...';

    const fileInput = document.getElementById('resumeFile');
    const file = fileInput.files[0];

    if (!file) {
        uploadStatus.innerHTML = '<div class="alert alert-danger">Please select a file to upload</div>';
        return;
    }

    // Check file type
    const allowedTypes = ['.pdf', '.docx', '.doc', '.txt'];
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

    if (!allowedTypes.includes(fileExtension)) {
        uploadStatus.innerHTML = '<div class="alert alert-danger">Invalid file type. Please upload PDF, DOCX, DOC, or TXT files only.</div>';
        return;
    }

    // Create form data for file upload
    const formData = new FormData();
    formData.append('resume', file);

    try {
        // Hard-coded user ID for PoC
        const userId = 1;

        const response = await fetch(`/users/${userId}/resume/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        uploadStatus.innerHTML = '<div class="alert alert-success">Resume uploaded successfully!</div>';

        // Reload profile with the new data
        loadProfile();
    } catch (error) {
        console.error('Error uploading resume:', error);
        uploadStatus.innerHTML = `<div class="alert alert-danger">Error uploading resume: ${error.message}</div>`;
    }
}

// Function to load and display jobs
async function loadJobs() {
    try {
        // For now, hardcode user ID to 1
        const userId = 1;
        const jobsContainer = document.getElementById('jobsList');
        jobsContainer.innerHTML = 'Loading jobs...';

        const response = await fetch(`/users/${userId}/jobs/`);

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const jobs = await response.json();

        if (jobs.length === 0) {
            jobsContainer.innerHTML = '<p class="placeholder">No jobs saved yet. Add a job using the form above.</p>';
            return;
        }

        let jobsHtml = '<div class="jobs-list">';

        jobs.forEach(job => {
            jobsHtml += `
                <div class="job-card" data-job-id="${job.id}">
                    <div class="job-title">${job.title || 'Untitled Job'}</div>
                    <div class="job-company">${job.company || 'Unknown Company'}</div>
                    ${job.ranking_score ? 
                        `<div class="job-score">Match: ${job.ranking_score}/10</div>` : 
                        '<div class="job-score unranked">Not ranked</div>'
                    }
                </div>
            `;
        });

        jobsHtml += '</div>';
        jobsContainer.innerHTML = jobsHtml;
    } catch (error) {
        console.error('Error loading jobs:', error);
        document.getElementById('jobsList').innerHTML = `
            <div class="alert alert-danger">
                <h4><i class="bi bi-exclamation-triangle-fill me-2"></i>Error Loading Jobs</h4>
                <p>${error.message}</p>
            </div>
        `;
    }
}

// Function to save job
async function saveJob() {
    const jobDescriptionTextarea = document.getElementById('jobDescription');
    const saveJobButton = document.getElementById('saveJobButton');
    const jobDescription = jobDescriptionTextarea.value.trim();

    if (!jobDescription) {
        alert('Please enter a job description before saving.');
        return;
    }

    // Show loading state
    const originalButtonText = saveJobButton.textContent;
    saveJobButton.disabled = true;
    saveJobButton.textContent = 'Saving...';

    // Optional: Add a spinner next to the text
    const spinner = document.createElement('span');
    spinner.className = 'spinner';
    spinner.style.display = 'inline-block';
    spinner.style.width = '16px';
    spinner.style.height = '16px';
    spinner.style.marginLeft = '8px';
    spinner.style.border = '2px solid rgba(0, 0, 0, 0.1)';
    spinner.style.borderTopColor = '#3498db';
    spinner.style.borderRadius = '50%';
    spinner.style.animation = 'spin 1s linear infinite';
    saveJobButton.appendChild(spinner);

    // Add the keyframe animation if it doesn't exist
    if (!document.getElementById('spinnerAnimation')) {
        const styleSheet = document.createElement('style');
        styleSheet.id = 'spinnerAnimation';
        styleSheet.textContent = `
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(styleSheet);
    }

    try {
        // For now, hardcode user ID to 1
        const userId = 1;

        // Inform user that LLM processing might take a moment
        jobDescriptionTextarea.value = 'Formatting job description with AI...';
        jobDescriptionTextarea.disabled = true;

        const response = await fetch(`/users/${userId}/jobs/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                title: 'New Job', // Will be updated by backend using LLM
                company: 'Unknown Company', // Will be updated by backend using LLM
                description: jobDescription
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        // Reset and clear the textarea
        jobDescriptionTextarea.value = ''; 
        jobDescriptionTextarea.disabled = false;

        // Reload jobs list to show new job
        loadJobs();

        // Optional: Show success message
        alert('Job saved successfully!');
    } catch (error) {
        console.error('Error saving job:', error);
        alert(`Error saving job: ${error.message}`);
        // Re-enable textarea on error
        jobDescriptionTextarea.disabled = false;
        jobDescriptionTextarea.value = jobDescription; // Restore original content
    } finally {
        // Reset button state
        saveJobButton.disabled = false;
        saveJobButton.textContent = originalButtonText;
        if (spinner && spinner.parentNode) {
            spinner.parentNode.removeChild(spinner);
        }
    }
}

// Function to get tailoring suggestions
async function getTailoringSuggestions() {
    const tailoringSuggestionsContainer = document.getElementById('tailoringSuggestions');
    const tailorButton = document.getElementById('tailorButton');

    // Get the currently selected job
    const selectedJobCard = document.querySelector('.job-card.active');
    if (!selectedJobCard) {
        alert('Please select a job first to get tailoring suggestions.');
        return;
    }

    const jobId = selectedJobCard.dataset.jobId;
    if (!jobId) {
        alert('Could not identify the selected job. Please try again.');
        return;
    }

    // Show loading state
    const originalButtonText = tailorButton.textContent;
    tailorButton.disabled = true;
    tailorButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Generating suggestions...';
    tailoringSuggestionsContainer.innerHTML = '<div class="alert alert-info">Analyzing your profile and the job description...</div>';

    try {
        // For now, hardcode user ID to 1 for PoC
        const userId = 1;

        // First, get the job description
        const jobResponse = await fetch(`/users/${userId}/jobs/${jobId}`);
        if (!jobResponse.ok) {
            throw new Error(`Error fetching job: ${jobResponse.status}`);
        }
        const jobData = await jobResponse.json();

        // Get job description from the job data
        let jobDescription = "";
        try {
            // Check if job description is JSON string
            if (typeof jobData.description === 'string' && jobData.description.trim().startsWith('{')) {
                const parsedDesc = JSON.parse(jobData.description);
                jobDescription = parsedDesc.description || jobData.description;
            } else {
                jobDescription = jobData.description;
            }
        } catch (e) {
            jobDescription = jobData.description;
        }

        // Call the tailoring suggestions endpoint
        const suggResponse = await fetch(`/users/${userId}/jobs/tailor-suggestions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job_description: jobDescription
            })
        });

        if (!suggResponse.ok) {
            const errorData = await suggResponse.json();
            throw new Error(errorData.detail || `HTTP error! status: ${suggResponse.status}`);
        }

        const suggestionData = await suggResponse.json();

        // Display suggestions with nice formatting
        if (suggestionData.suggestions) {
            // Format suggestions as a list if they contain line breaks
            let formattedSuggestions = suggestionData.suggestions;
            if (formattedSuggestions.includes('\n')) {
                const suggItems = formattedSuggestions.split('\n').filter(s => s.trim());
                if (suggItems.length > 1) {
                    formattedSuggestions = '<ul>' + 
                        suggItems.map(sugg => `<li>${sugg}</li>`).join('') + 
                        '</ul>';
                }
            }

            tailoringSuggestionsContainer.innerHTML = `
                <div class="card border-0">
                    <div class="card-header bg-light">
                        <i class="bi bi-lightbulb me-2"></i>Tailoring Suggestions
                    </div>
                    <div class="card-body">
                        <div class="tailoring-content">${formattedSuggestions}</div>
                    </div>
                </div>
            `;
        } else {
            tailoringSuggestionsContainer.innerHTML = `<div class="alert alert-warning">No suggestions were generated. Try selecting a different job.</div>`;
        }
    } catch (error) {
        console.error('Error getting tailoring suggestions:', error);
        tailoringSuggestionsContainer.innerHTML = `
            <div class="alert alert-danger">
                <h4><i class="bi bi-exclamation-triangle-fill me-2"></i>Error</h4>
                <p>${error.message}</p>
            </div>
        `;
    } finally {
        // Reset button state
        tailorButton.disabled = false;
        tailorButton.innerHTML = originalButtonText;
    }
}

// Handle clicking on a job in the jobs list
function handleJobClick(event) {
    // Find the closest job-card element from the click target
    const jobCard = event.target.closest('.job-card');
    if (!jobCard) return;

    const jobId = jobCard.dataset.jobId;
    if (!jobId) return;

    // Mark the clicked job as active
    const allJobCards = document.querySelectorAll('.job-card');
    allJobCards.forEach(card => card.classList.remove('active'));
    jobCard.classList.add('active');

    // Load and display the job details
    showJobDetails(jobId, 1); // Hardcoded user ID to 1 for PoC
}

// Function to handle job actions (like ranking)
function handleJobActions(event) {
    // Check if the clicked element is the rank job button
    if (event.target.id === 'rankJobButton' || event.target.closest('#rankJobButton')) {
        const button = event.target.id === 'rankJobButton' ? event.target : event.target.closest('#rankJobButton');
        const jobId = button.dataset.jobId;

        if (jobId) {
            rankJob(jobId, 1); // Hardcoded user ID to 1 for PoC
        }
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

        // Try to parse the description as JSON (for formatted job details)
        let parsedJobDetails = {};
        try {
            // If the description is a JSON string, parse it
            if (typeof job.description === 'string' && job.description.trim().startsWith('{')) {
                parsedJobDetails = JSON.parse(job.description);
            } else {
                // Handle legacy format where description is just text
                parsedJobDetails = { description: job.description };
            }
        } catch (e) {
            console.error('Error parsing job description as JSON:', e);
            // Keep the original description if parsing fails
            parsedJobDetails = { description: job.description || '' };
        }

        // Check if parsedJobDetails is an object to avoid errors
        if (typeof parsedJobDetails !== 'object' || parsedJobDetails === null) {
            parsedJobDetails = { description: job.description || 'No description available' };
        }

        // Create job details card with Bootstrap styling
        let jobDetailsHTML = `
            <div class="card border-0 mb-3">
                <div class="card-body p-0">
                    <h5 class="d-flex align-items-center">
                        <i class="bi bi-briefcase me-2"></i>
                        <span>${(parsedJobDetails.title || job.title || 'Job Details')}</span>
                    </h5>
                    <p class="card-subtitle mb-3 text-muted">
                        <i class="bi bi-building me-1"></i>${(parsedJobDetails.company || job.company || 'Unknown Company')}
                    </p>
                    ${parsedJobDetails.location ? `<p class="card-subtitle mb-3 text-muted"><i class="bi bi-geo-alt me-1"></i>${parsedJobDetails.location}</p>` : ''}
                </div>
            </div>
        `;

        // Add description section - safely check if description exists
        if (parsedJobDetails.description) {
            // Process the job description to maintain proper formatting
            let formattedDescription = parsedJobDetails.description;

            // 1. Replace line breaks with <br> tags
            formattedDescription = formattedDescription.replace(/\n/g, '<br>');

            // 2. Convert bullet point patterns to HTML lists
            const bulletPatterns = [
                /^[\s]*[-•●\*][\s]+(.+)$/gm,  // Matches common bullet point formats
                /^[\s]*\d+\.[\s]+(.+)$/gm    // Matches numbered lists
            ];

            // Check for bullet points and create HTML lists if found
            let hasBulletPoints = false;
            for (const pattern of bulletPatterns) {
                if (pattern.test(formattedDescription)) {
                    hasBulletPoints = true;
                    break;
                }
            }

            // 3. Enhance section headers (text that appears to be headings)
            formattedDescription = formattedDescription.replace(/^(.{3,50}):(?:\s*)$/gm, '<h6 class="mt-3">$1</h6>');

            // 4. Add spacing between paragraphs
            formattedDescription = formattedDescription.replace(/<br><br>/g, '</p><p>');

            jobDetailsHTML += `
                <div class="card mb-3">
                    <div class="card-header d-flex align-items-center bg-light">
                        <i class="bi bi-info-circle me-2"></i>Overview
                    </div>
                    <div class="card-body job-description">
                        <div class="job-description-content">${formattedDescription}</div>
                    </div>
                </div>
            `;

            // Add CSS styles for job description if not already added
            if (!document.getElementById('jobDescriptionStyles')) {
                const styleSheet = document.createElement('style');
                styleSheet.id = 'jobDescriptionStyles';
                styleSheet.textContent = `
                    .job-description {
                        font-size: 0.95rem;
                        line-height: 1.5;
                    }
                    .job-description-content {
                        white-space: pre-wrap;
                    }
                    .job-description-content p {
                        margin-bottom: 1rem;
                    }
                    .job-description-content h6 {
                        font-weight: 600;
                        margin-top: 1.5rem;
                        margin-bottom: 0.75rem;
                        color: #2c5282;
                    }
                    .job-description-content ul, .job-description-content ol {
                        padding-left: 2rem;
                        margin-bottom: 1rem;
                    }
                    .job-description-content li {
                        margin-bottom: 0.5rem;
                    }
                `;
                document.head.appendChild(styleSheet);
            }
        }

        // Add responsibilities section if available - safely check array properties
        if (Array.isArray(parsedJobDetails.responsibilities) && parsedJobDetails.responsibilities.length > 0) {
            const responsibilitiesList = parsedJobDetails.responsibilities
                .map(resp => `<li>${resp || ''}</li>`)
                .join('');

            jobDetailsHTML += `
                <div class="card mb-3">
                    <div class="card-header d-flex align-items-center bg-light">
                        <i class="bi bi-list-task me-2"></i>Responsibilities
                    </div>
                    <div class="card-body">
                        <ul class="mb-0">${responsibilitiesList}</ul>
                    </div>
                </div>
            `;
        }

        // Add requirements section if available - safely check array properties
        if (Array.isArray(parsedJobDetails.requirements) && parsedJobDetails.requirements.length > 0) {
            const requirementsList = parsedJobDetails.requirements
                .map(req => `<li>${req || ''}</li>`)
                .join('');

            jobDetailsHTML += `
                <div class="card mb-3">
                    <div class="card-header d-flex align-items-center bg-light">
                        <i class="bi bi-check-square me-2"></i>Requirements
                    </div>
                    <div class="card-body">
                        <ul class="mb-0">${requirementsList}</ul>
                    </div>
                </div>
            `;
        }

        // Add benefits section if available - safely check array properties
        if (Array.isArray(parsedJobDetails.benefits) && parsedJobDetails.benefits.length > 0) {
            const benefitsList = parsedJobDetails.benefits
                .map(benefit => `<li>${benefit || ''}</li>`)
                .join('');

            jobDetailsHTML += `
                <div class="card mb-3">
                    <div class="card-header d-flex align-items-center bg-light">
                        <i class="bi bi-gift me-2"></i>Benefits
                    </div>
                    <div class="card-body">
                        <ul class="mb-0">${benefitsList}</ul>
                    </div>
                </div>
            `;
        }

        // Add raw description as fallback when no structured data is available
        if (!parsedJobDetails.description && 
            (!Array.isArray(parsedJobDetails.responsibilities) || parsedJobDetails.responsibilities.length === 0) &&
            (!Array.isArray(parsedJobDetails.requirements) || parsedJobDetails.requirements.length === 0)) {

            jobDetailsHTML += `
                <div class="card mb-3">
                    <div class="card-header d-flex align-items-center bg-light">
                        <i class="bi bi-file-text me-2"></i>Job Description
                    </div>
                    <div class="card-body">
                        <pre class="mb-0 bg-light p-3 rounded">${job.description || 'No description provided'}</pre>
                    </div>
                </div>
            `;
        }

        if (job.ranking_score) {
            // Define color based on score
            let scoreColorClass = 'text-danger';
            if (job.ranking_score >= 7) scoreColorClass = 'text-success';
            else if (job.ranking_score >= 5) scoreColorClass = 'text-warning';

            jobDetailsHTML += `
                <div class="card border-0 mb-3">
                    <div class="card-header bg-light">
                        <i class="bi bi-graph-up me-2"></i>Match Analysis
                    </div>
                    <div class="card-body">
                        <h5 class="${scoreColorClass} mb-3">
                            <i class="bi bi-star-fill me-2"></i>
                            Score: ${job.ranking_score}/10
                        </h5>
                        <div class="alert alert-light">
                            ${job.ranking_explanation || 'No explanation provided.'}
                        </div>
                    </div>
                </div>
            `;
        }

        jobDetailsHTML += `
            <button id="rankJobButton" class="btn ${job.ranking_score ? 'btn-outline-primary' : 'btn-primary'}" data-job-id="${job.id}">
                <i class="bi bi-calculator me-1"></i>${job.ranking_score ? 'Re-rank Job' : 'Rank Job'}
            </button>
        `;

        jobDetailsContainer.innerHTML = jobDetailsHTML;

    } catch (error) {
        console.error('Error showing job details:', error);
        document.getElementById('jobDetails').innerHTML = `
            <div class="alert alert-danger">
                <h4><i class="bi bi-exclamation-triangle-fill me-2"></i>Error Loading Job Details</h4>
                <p>${error.message}</p>
            </div>
        `;
    }
}

// Function to rank a job
async function rankJob(jobId, userId) {
    const rankButton = document.getElementById('rankJobButton');
    if (rankButton) {
        rankButton.disabled = true;
        rankButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Ranking...';
    }

    try {
        const response = await fetch(`/users/${userId}/jobs/${jobId}/rank`, {
            method: 'POST'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        // Reload job details with ranking
        showJobDetails(jobId, userId);

        // Also refresh the jobs list to show updated ranking
        loadJobs();
    } catch (error) {
        console.error('Error ranking job:', error);
        alert(`Error ranking job: ${error.message}`);

        // Re-enable the button
        if (rankButton) {
            rankButton.disabled = false;
            rankButton.innerHTML = '<i class="bi bi-calculator me-1"></i>Rank Job';
        }
    }
}
