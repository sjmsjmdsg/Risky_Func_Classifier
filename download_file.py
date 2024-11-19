import os
import requests
import base64
import time

def make_request(url, github_api_key, retries=3, delay=5):
    headers = {
        "Authorization": f"token {github_api_key}",
        "Accept": "application/vnd.github.v3+json"
    }
    for _ in range(retries):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)
    raise Exception(f"Failed to make request after {retries} retries: {url}")

def get_commit_info(repo_owner, repo_name, commit_sha, github_api_key):
    url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{commit_sha}'
    response = make_request(url, github_api_key)
    if response.status_code == 200:
        data = response.json()
        files = data.get('files', [])
        parent_shas = [parent['sha'] for parent in data.get('parents', [])]
        parent_sha = parent_shas[0] if parent_shas else None  # Get the SHA of the parent commit
        return files, parent_sha
    return [], None

def download_file(repo_owner, repo_name, file_path, dest_path, commit_sha, github_api_key):
    url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}?ref={commit_sha}'
    response = make_request(url, github_api_key)
    if response.status_code == 200:
        file_content = base64.b64decode(response.json().get('content', ''))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, 'wb') as f:
            f.write(file_content)
        #print(f"Downloaded file to {dest_path}")

def download_commit_files(commit_link, github_api_key):
    # Extract `repo_owner`, `repo_name`, and `commit_sha`
    parts = commit_link.split('/')
    repo_owner = parts[3]
    repo_name = parts[4]
    commit_sha = parts[-1]

    # Get information about the files changed in the commit and the SHA of the parent commit
    files, parent_commit_sha = get_commit_info(repo_owner, repo_name, commit_sha, github_api_key)
    if not files:
        #print(f"Failed to retrieve files for commit {commit_sha}")
        return
    if not parent_commit_sha:
        #print(f"Failed to retrieve parent commit SHA for {commit_sha}")
        return

    # Create folders for current_repo and previous_repo
    current_repo_path = f"{os.getcwd()}/current_repo"
    previous_repo_path = f"{os.getcwd()}/previous_repo"
    os.makedirs(current_repo_path, exist_ok=True)
    os.makedirs(previous_repo_path, exist_ok=True)

    # Download the current version and parent version of each file
    for file in files:
        file_path = file['filename']
        file_status = file['status']

        # Download the current version of the file
        if file_status != 'removed':
            dest_file_path = os.path.join(current_repo_path, file_path)
            download_file(repo_owner, repo_name, file_path, dest_file_path, commit_sha, github_api_key)

        # Download the parent version of the file
        if file_status in ['modified', 'removed']:
            dest_previous_path = os.path.join(previous_repo_path, file_path)
            download_file(repo_owner, repo_name, file_path, dest_previous_path, parent_commit_sha, github_api_key)

    #print("All files downloaded.")

# Example usage
# commit_link = "https://github.com/repo_owner/repo_name/commit/commit_sha"
# github_api_key = "your_github_token"
# download_commit_files(commit_link, github_api_key)
