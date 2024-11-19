import argparse
import openai
import requests
import json
import re
import time
import os
import shutil
from download_file import download_commit_files
from candidate_list_generator import generate_candidate_list
from graph_generator import generate_call_graph_dot

# Helper function for making GitHub API requests
def make_request(url, retries=3, delay=5, github_api_key=None):
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

# Get NVD information
def get_nvd_info(cve_id, github_api_key):
    url = f'https://nvd.nist.gov/vuln/detail/{cve_id}'
    response = make_request(url, github_api_key=github_api_key)
    if response.status_code == 200:
        description_pattern = re.compile(r'<p data-testid="vuln-description">(.*?)</p>', re.DOTALL)
        cwe_pattern = re.compile(
            r'<tr data-testid="vuln-CWEs-row-\d+">\s*<td data-testid="vuln-CWEs-link-\d+">\s*<a href="http://cwe.mitre.org/data/definitions/\d+.html" target="_blank" rel="noopener noreferrer">(CWE-\d+)</a>\s*</td>\s*<td\s*data-testid="vuln-CWEs-link-\d+">(.*?)</td>',
            re.DOTALL
        )

        description = description_pattern.search(response.text)
        description = description.group(1).strip() if description else None

        cwe_matches = cwe_pattern.findall(response.text)
        cwe_ids = {cwe_id: cwe_name.strip() for cwe_id, cwe_name in cwe_matches}
        if not cwe_ids:
            cwe_ids["no"] = "NVD-CWE-noinfo"

        return description, cwe_ids
    return None, {}

# Get GitHub commit information
def get_commit_info(repo_owner, repo_name, commit_sha, github_api_key):
    url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{commit_sha}'
    response = make_request(url, github_api_key=github_api_key)
    if response.status_code == 200:
        data = response.json()
        commit_message = data['commit']['message']
        files = data.get('files', [])
        repo_info = {
            'repo_owner': repo_owner,
            'repo_name': repo_name,
            'commit_sha': commit_sha,
            'url': f'git@github.com:{repo_owner}/{repo_name}.git'
        }
        return commit_message, files, repo_info
    return None, None, None

# Generate prompt for GPT-4
def generate_prompt(cve_id, commit_link, candidate_list, call_graph_dot, github_api_key):
    try:
        # Extract GitHub repository information
        parts = commit_link.split('/')
        repo_owner = parts[3]
        repo_name = parts[4]
        commit_sha = parts[-1]

        # Get NVD and GitHub information
        description, cwe_ids = get_nvd_info(cve_id, github_api_key)
        commit_message, files, repo_info = get_commit_info(repo_owner, repo_name, commit_sha, github_api_key)
        if not description or not commit_message:
            raise Exception(f'Failed to retrieve information for {cve_id}')

        # Build file information
        files_info = [{"filename": file["filename"], "patch": file.get("patch", "")} for file in files]

        # Construct references
        references_info = {"CVE": [cve_id]}

        # Full prompt content
        prompt_content = {
            "role": "You are a security expert with knowledge of NVD and CVE, proficient in program analysis and vulnerabilities detection.",
            "task": "Identify and explain risky functions in the 'before' code snippets of the provided commit patch, following the given rules.",
            "information": {
                "CVE": {
                    "CVE_ID": cve_id,
                    "CVE_Description": description,
                    "CWE_IDs": cwe_ids
                },
                "Commit": {
                    "message": commit_message,
                    "files": files_info
                },
                "Candidate List": candidate_list,
                "Call Graph": call_graph_dot,
                "References": references_info
            },
            "rules": {
                "1": "A risky function refers to functions associated with vulnerabilities or system instability.",
                "2": "Consider both upstream and downstream risky functions in the project.",
                "3": "Only include functions directly modified in the patch as risky functions.",
                "4": "A vulnerable function can be a risky function if it is modified.",
                "5": "Exclude test functions.",
                "6": "Please output the risky function and provide a detailed explanation for each identified function. Just output these two things in json! Output format: 'Risky function:\n 1.[file_name]/[function_name]\n 2.[file_name]/[function_name]\n...\n Explanation:...'"
            }
        }

        return prompt_content

    except Exception as e:
        raise Exception(f"Error generating prompt: {e}")

# Call GPT-4
def call_gpt_4o(prompt_content, openai_key):
    openai.api_key = openai_key
    messages = [
        {"role": "system", "content": f"Role: {prompt_content['role']}"},
        {"role": "user", "content": json.dumps(prompt_content, indent=2)},
        {"role": "assistant",
         "content": "Please return only the JSON object, with no additional tags, markers, or formatting."}
    ]

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.0
    )

    return response['choices'][0]['message']['content']

# Main process for handling CVE and Commit Link
def process_cve(cve_id, commit_link, github_api_key, openai_key):
    try:
        # Step 1: Download commit files
        #print("Starting file download...")
        download_commit_files(commit_link, github_api_key)
        #print("Download completed.")

        # Step 2: Generate candidate list
        print("Generating candidate list...")
        candidate_list = generate_candidate_list()
        print("Candidate List:", candidate_list)

        # Step 3: Generate call graph as DOT format string
        print("Generating call graph...")
        call_graph_dot = generate_call_graph_dot(candidate_list, os.getcwd())
        print("Call Graph DOT Format:", call_graph_dot)

        # Step 4: Generate the prompt with candidate list and call graph
        prompt_content = generate_prompt(cve_id, commit_link, candidate_list, call_graph_dot, github_api_key)

        # Step 5: Call GPT-4 and get the response
        gpt_response = call_gpt_4o(prompt_content, openai_key)

        # Print GPT-4 generated response
        #print("GPT-4 Response:")
        print(gpt_response)

    except Exception as e:
        print(f"Error: {str(e)}")

    finally:
        # Clean up downloaded files after processing
        for folder in ["previous_repo", "current_repo"]:
            if os.path.exists(folder):
                try:
                    shutil.rmtree(folder)
                    #print(f"Deleted folder: {folder}")
                except Exception as e:
                    print(f"Failed to delete folder {folder}: {e}")

# Command-line argument parsing
def main():
    parser = argparse.ArgumentParser(description="Process CVE ID and Commit Link with GPT-4.")
    parser.add_argument('--cve_id', required=True, help="The CVE ID (e.g., CVE-2020-13401).")
    parser.add_argument('--commit_link', required=True, help="The GitHub commit link.")
    parser.add_argument('--github_key', required=True, help="Your GitHub API Key.")
    parser.add_argument('--openai_key', required=True, help="Your OpenAI API Key.")

    args = parser.parse_args()

    # Execute the process with provided arguments
    process_cve(args.cve_id, args.commit_link, args.github_key, args.openai_key)

if __name__ == "__main__":
    main()
