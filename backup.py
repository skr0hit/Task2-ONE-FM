#!/usr/bin/env python3

import docker          # Library to interact with the Docker daemon (control containers, etc.)
import os              # Operating system functions (like creating directories, joining paths)
import datetime        # For getting the current date and time (used for timestamps)
import subprocess      # To run external commands like 'docker cp'
import sys             # System-specific parameters and functions (like exiting the script)
import logging         # For recording messages (info, errors) during script execution

# --- Configuration ---
# These variables make the script easy to adapt
PROJECT_NAME = "app" # Your Docker Compose project name
SITE_NAME = "frontend"           # The name of the Frappe site
HOST_BACKUP_DIR = "/home/ubuntu/frappe_backups" # Where backups are saved ON THE EC2 SERVER
LOG_FILE = os.path.join(HOST_BACKUP_DIR, "backup_py.log") # Path to the log file
# --- End Configuration ---

# --- Setup Logging ---
# Configures logging to write messages to both the LOG_FILE and the console
logging.basicConfig(
    level=logging.INFO, # Record INFO level messages and above (WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(levelname)s - %(message)s', # Log message format
    handlers=[
        logging.FileHandler(LOG_FILE),     # Handler to write logs to the file
        logging.StreamHandler(sys.stdout) # Handler to print logs to the console
    ]
)

def find_latest_backup(container, container_backup_dir, file_pattern):
    """Finds the most recent file matching a pattern in the container's backup dir."""
    logging.info(f"Searching for files matching '{file_pattern}' in container path '{container_backup_dir}'...")
    try:
        # Construct a shell command to run inside the container:
        # ls -t: List files sorted by modification time (newest first)
        # | grep '{file_pattern}': Filter the list to only include files matching the pattern
        # | head -n 1: Take only the first line (the newest file)
        cmd = f"ls -t {container_backup_dir} | grep '{file_pattern}' | head -n 1"
        # Execute the command inside the container using the container's shell
        exit_code, output = container.exec_run(cmd=["/bin/sh", "-c", cmd], demux=False)

        # Check if the command ran successfully and produced output
        if exit_code == 0 and output:
            filename = output.decode('utf-8').strip() # Decode bytes to string and remove extra whitespace
            if filename: # Make sure a filename was actually found
                logging.info(f"Found latest backup file: {filename}")
                return filename # Return the found filename
        # If no file was found or the command failed
        logging.warning(f"No backup file found matching pattern '{file_pattern}' in {container_backup_dir}")
        return None
    except Exception as e:
        # Catch any errors during command execution
        logging.error(f"Error listing backups in container: {e}")
        return None

def main():
    """Runs the main backup process."""
    logging.info(f"Starting automated backup for project '{PROJECT_NAME}', site '{SITE_NAME}'...")

    # Ensure the directory on the EC2 host for storing backups exists
    try:
        os.makedirs(HOST_BACKUP_DIR, exist_ok=True) # exist_ok=True prevents error if dir already exists
    except OSError as e:
        logging.error(f"Could not create host backup directory '{HOST_BACKUP_DIR}': {e}")
        sys.exit(1) # Exit script with an error code

    try:
        # Initialize the Docker client - connects to the Docker daemon via the socket
        client = docker.from_env()

        # 1. Find the running backend container
        # Docker Compose typically names containers like project_service_replica (e.g., my-project-name-backend-1)
        expected_container_name = f"{PROJECT_NAME}-backend-1"
        container = None
        try:
            # Get the container object by its name
            container = client.containers.get(expected_container_name)
            # Check if the found container is actually running
            if container.status != 'running':
                 logging.error(f"Backend container '{expected_container_name}' found but is not running (status: {container.status}).")
                 sys.exit(1)
            logging.info(f"Found running backend container: {container.name} ({container.short_id})")
        except docker.errors.NotFound: # Specific error if container doesn't exist
            logging.error(f"Backend container '{expected_container_name}' not found. Is the stack running?")
            sys.exit(1)
        except Exception as e: # Catch other potential Docker connection errors
             logging.error(f"Error connecting to Docker or finding container: {e}")
             sys.exit(1)

        # 2. Execute the 'bench backup' command inside the container
        container_backup_dir = f"/home/frappe/frappe-bench/sites/{SITE_NAME}/private/backups" # Path inside container
        backup_command = f"/home/frappe/.local/bin/bench --site {SITE_NAME} backup"
        logging.info(f"Running '{backup_command}' inside the container...")

        # Run the command as the 'frappe' user within the container
        exit_code, output = container.exec_run(cmd=backup_command, demux=False, user='frappe')

        # Check if the command was successful (exit code 0 usually means success)
        if exit_code != 0:
            logging.error(f"'bench backup' command failed inside the container. Exit code: {exit_code}")
            logging.error(f"Output:\n{output.decode('utf-8')}")
            # Decide whether to continue or exit if bench backup fails (currently continues)
        else:
             logging.info("'bench backup' completed successfully.")
             logging.debug(f"Output:\n{output.decode('utf-8')}") # Log full output only if debugging needed

        # 3. Find and copy the database backup file (.sql.gz)
        # Use the helper function with a regex pattern to find the DB backup
        db_backup_file = find_latest_backup(container, container_backup_dir, r'\-database\.sql\.gz$')
        if db_backup_file:
            current_date = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") # Get timestamp for filename
            host_db_path = os.path.join(HOST_BACKUP_DIR, f"{current_date}_{db_backup_file}") # Full path on EC2 host
            container_db_path = f"{container_backup_dir}/{db_backup_file}" # Full path inside container
            logging.info(f"Copying database backup '{db_backup_file}' to host path '{host_db_path}'...")
            try:
                # Use 'docker cp' command via subprocess for simplicity
                # Format: docker cp <containerId>:<containerPath> <hostPath>
                cp_command = ["docker", "cp", f"{container.id}:{container_db_path}", host_db_path]
                # Run the command, capture output, check for errors
                result = subprocess.run(cp_command, capture_output=True, text=True, check=True)
                logging.info("Database backup copied successfully.")
            except subprocess.CalledProcessError as e: # Catch errors specifically from the subprocess
                logging.error(f"Failed to copy database backup file from container: {e}")
                logging.error(f"Stderr: {e.stderr}") # Print the error output from docker cp
            except Exception as e: # Catch any other unexpected errors during copy
                 logging.error(f"An unexpected error occurred during DB copy: {e}")

        # 4. Find and copy the files backup file (-files.tar)
        # Similar process as for the database backup, but with a different file pattern
        files_backup_file = find_latest_backup(container, container_backup_dir, r'\-files\.tar$')
        if files_backup_file:
             current_date = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
             host_files_path = os.path.join(HOST_BACKUP_DIR, f"{current_date}_{files_backup_file}")
             container_files_path = f"{container_backup_dir}/{files_backup_file}"
             logging.info(f"Copying files backup '{files_backup_file}' to host path '{host_files_path}'...")
             try:
                cp_command = ["docker", "cp", f"{container.id}:{container_files_path}", host_files_path]
                result = subprocess.run(cp_command, capture_output=True, text=True, check=True)
                logging.info("Files backup copied successfully.")
             except subprocess.CalledProcessError as e:
                logging.error(f"Failed to copy files backup file from container: {e}")
                logging.error(f"Stderr: {e.stderr}")
             except Exception as e:
                 logging.error(f"An unexpected error occurred during files copy: {e}")

        logging.info("Backup process finished.")

    except Exception as e:
        # Catch any broad errors during the main process (like Docker connection issues)
        logging.error(f"An unexpected error occurred during the backup process: {e}")
        sys.exit(1)

# This standard Python construct ensures the code runs only when the script is executed directly
if __name__ == "__main__":
    # Make sure the backup log directory exists before trying to log to it
    os.makedirs(HOST_BACKUP_DIR, exist_ok=True)
    main() # Call the main function to start the backup