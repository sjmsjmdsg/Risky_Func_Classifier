import os
import pandas as pd
import requests

def read_excel(file_path):
    print(f"Reading Excel file: {file_path}")
    return pd.read_excel(file_path)

def get_github_commit_data(api_url):
    github_token = 'Token'  # Replace this with your actual GitHub token
    headers = {
        'Authorization': f'token {github_token}'
    }
    print(f"Requesting GitHub API: {api_url}")
    response = requests.get(api_url, headers=headers)
    if response.status_code == 200:
        print(f"Data retrieved successfully from {api_url}")
        return response.json()
    else:
        print(f"Failed to retrieve data from {api_url}, status code: {response.status_code}")
        return None

def should_ignore_file(filename, filepath):
    excluded_extensions = [
        ".md", ".txt", ".docx", ".pdf", ".rst", ".changes", ".rdoc", ".mdown",
        ".command", ".out", ".err", ".stderr", ".stdout", ".test",
        ".jpg", ".png", ".svg", ".mp4", ".gif", ".exr",
        ".csv", ".rdf",
        ".ttf", ".otf", ".woff", ".woff2",
        ".mock", ".stub", ".fake",
        ".pptx", ".key",
        ".bak", ".zip", ".gz", ".rar",
        ".gitignore"
    ]

    excluded_filenames = [
        "changelog", "news", "changes", "version", "readme", "license", "authors", "todo", "history",
        "copying", "relnotes", "thanks", "notice", "whatsnew", "notes", "release_notes",
        "testlist", "testsuite", "test"
    ]

    excluded_paths = ["note", "license", "test", "Test"]

    if any(filename.lower().endswith(ext) for ext in excluded_extensions):
        return True

    actual_filename = os.path.basename(filepath)

    if any(keyword in actual_filename.lower() for keyword in excluded_filenames):
            return True

    if any(keyword in filepath.lower() for keyword in excluded_paths):
        return True

    return False
