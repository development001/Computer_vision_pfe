import json
import os
import threading

# Persistence file
PERSISTENCE_FILE = os.path.join(os.path.dirname(__file__), 'persistence.json')
persistence_lock = threading.Lock()

def save_state(cameras, jobs, jobs_lock):
    """Saves current cameras and job configurations to a JSON file."""
    data = {
        'cameras': cameras,
        'jobs': {}
    }
    # Create a snapshot of the data to save
    with jobs_lock:
        for jid, job in jobs.items():
            # Only save the configuration, not the worker instance
            job_data = job.copy()
            if 'worker' in job_data:
                del job_data['worker']
            data['jobs'][jid] = job_data
            
    try:
        with persistence_lock:
            with open(PERSISTENCE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving persistence file: {e}")

def load_state():
    """Loads cameras and job configurations from the JSON file."""
    if not os.path.exists(PERSISTENCE_FILE):
        return {}, {}

    try:
        with open(PERSISTENCE_FILE, 'r') as f:
            data = json.load(f)
            
        cameras = data.get('cameras', {})
        jobs_config = data.get('jobs', {})
        
        print(f"Loaded {len(cameras)} cameras and {len(jobs_config)} jobs from persistence.")
        return cameras, jobs_config
                
    except Exception as e:
        print(f"Error loading persistence file: {e}")
        return {}, {}
