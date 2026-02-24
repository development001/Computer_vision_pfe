// Toggle tracker type specific options
function toggleTrackerOptions() {
    const trackerType = document.getElementById('trackerType').value;
    const botsortOptions = document.getElementById('botsortOptions');
    
    if (trackerType === 'botsort') {
        botsortOptions.style.display = 'block';
    } else {
        botsortOptions.style.display = 'none';
    }
}

// Clear form function
function clearForm() {
    document.getElementById('trackerForm').reset();
    document.getElementById('botsortOptions').style.display = 'none';
}

// Load saved tracker configurations
async function loadSavedTrackers() {
    try {
        const response = await fetch('/trackers');
        if (response.ok) {
            const trackers = await response.json();
            displaySavedTrackers(trackers);
        } else {
            document.getElementById('savedTrackers').innerHTML = 
                '<p class="error">Failed to load tracker configurations</p>';
        }
    } catch (error) {
        console.error('Error loading trackers:', error);
        document.getElementById('savedTrackers').innerHTML = 
            '<p class="error">Error loading tracker configurations</p>';
    }
}

// Display saved tracker configurations
function displaySavedTrackers(trackers) {
    const container = document.getElementById('savedTrackers');
    
    if (!trackers || trackers.length === 0) {
        container.innerHTML = '<p>No tracker configurations found.</p>';
        return;
    }
    
    container.innerHTML = trackers.map(tracker => `
        <div class="tracker-card" onclick="selectTracker('${tracker.name}')">
            <h4>${tracker.name}</h4>
            <span class="tracker-type ${tracker.config.tracker_type}">${tracker.config.tracker_type}</span>
            <div class="tracker-params">
                <div>High Thresh: ${tracker.config.track_high_thresh}</div>
                <div>Low Thresh: ${tracker.config.track_low_thresh}</div>
                <div>Buffer: ${tracker.config.track_buffer}</div>
                ${tracker.config.tracker_type === 'botsort' ? 
                    `<div>GMC: ${tracker.config.gmc_method || 'sparseOptFlow'}</div>` : ''}
            </div>
            <div class="actions">
                <button class="btn-delete" onclick="event.stopPropagation(); deleteTracker('${tracker.name}')">
                    Delete
                </button>
            </div>
        </div>
    `).join('');
}

// Select tracker for use in jobs
function selectTracker(trackerName) {
    // Store selected tracker in session storage for jobs page
    sessionStorage.setItem('selectedTracker', trackerName);
    
    // Show success message
    showNotification(`Tracker "${trackerName}" selected for jobs`, 'success');
    
    // Redirect to jobs page
    setTimeout(() => {
        window.location.href = 'jobs.html';
    }, 1000);
}

// Delete tracker configuration
async function deleteTracker(trackerName) {
    if (!confirm(`Are you sure you want to delete tracker "${trackerName}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/trackers/${trackerName}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification(`Tracker "${trackerName}" deleted successfully`, 'success');
            loadSavedTrackers(); // Reload the list
        } else {
            showNotification('Failed to delete tracker', 'error');
        }
    } catch (error) {
        console.error('Error deleting tracker:', error);
        showNotification('Error deleting tracker', 'error');
    }
}

// Show notification
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        z-index: 1000;
        opacity: 0;
        transform: translateY(-20px);
        transition: all 0.3s ease;
    `;
    
    if (type === 'success') {
        notification.style.background = '#10b981';
    } else if (type === 'error') {
        notification.style.background = '#ef4444';
    } else {
        notification.style.background = '#3b82f6';
    }
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateY(0)';
    }, 10);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateY(-20px)';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Handle form submission
document.getElementById('trackerForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const trackerName = document.getElementById('trackerName').value.trim();
    const trackerType = document.getElementById('trackerType').value;
    
    if (!trackerName || !trackerType) {
        showNotification('Please fill in all required fields', 'error');
        return;
    }
    
    // Prepare tracker configuration
    const trackerConfig = {
        tracker_type: trackerType,
        track_buffer: parseInt(document.getElementById('trackBuffer').value) || 30,
        track_high_thresh: parseFloat(document.getElementById('trackHighThresh').value) || 0.5,
        track_low_thresh: parseFloat(document.getElementById('trackLowThresh').value) || 0.1,
        new_track_thresh: parseFloat(document.getElementById('newTrackThresh').value) || 0.6,
        match_thresh: parseFloat(document.getElementById('matchThresh').value) || 0.8,
        fuse_score: document.getElementById('fuseScore').checked
    };
    
    // Add BoTSORT specific parameters if selected
    if (trackerType === 'botsort') {
        trackerConfig.gmc_method = document.getElementById('gmcMethod').value;
        trackerConfig.proximity_thresh = parseFloat(document.getElementById('proximityThresh').value) || 0.5;
        trackerConfig.appearance_thresh = parseFloat(document.getElementById('appearanceThresh').value) || 0.25;
        trackerConfig.with_reid = document.getElementById('withReid').checked;
    }
    
    try {
        const response = await fetch('/trackers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: trackerName,
                config: trackerConfig
            })
        });
        
        if (response.ok) {
            showNotification(`Tracker "${trackerName}" saved successfully!`, 'success');
            clearForm();
            loadSavedTrackers(); // Reload the list
        } else {
            const error = await response.text();
            showNotification(`Failed to save tracker: ${error}`, 'error');
        }
    } catch (error) {
        console.error('Error saving tracker:', error);
        showNotification('Error saving tracker configuration', 'error');
    }
});

// Initialize page
window.addEventListener('DOMContentLoaded', function() {
    loadSavedTrackers();
    
    // Check if we have a selected tracker from session storage
    const selectedTracker = sessionStorage.getItem('selectedTracker');
    if (selectedTracker) {
        showNotification(`Using tracker: ${selectedTracker}`, 'info');
        sessionStorage.removeItem('selectedTracker');
    }
});