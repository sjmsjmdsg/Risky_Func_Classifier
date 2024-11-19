import os
from handlers.go_handler import GoHandler
from handlers.c_handler import CHandler
from handlers.java_handler import JavaHandler
from handlers.cpp_handler import CppHandler
from handlers.php_handler import PhpHandler
from handlers.javascript_handler import JavaScriptHandler
from handlers.python_handler import PythonHandler
from handlers.ruby_handler import RubyHandler

def get_handler_for_extension(extension):
    if extension == ".go":
        return GoHandler()
    elif extension == ".c" or extension == ".h":
        return CHandler()
    elif extension == ".java":
        return JavaHandler()
    elif extension in [".cpp", ".cc", ".cxx", ".hpp"]:
        return CppHandler()
    elif extension == ".php":
        return PhpHandler()
    elif extension == ".js":
        return JavaScriptHandler()
    elif extension in [".py", ".pyx"]:
        return PythonHandler()
    elif extension == ".rb":
        return RubyHandler()
    else:
        print(f"Unknown file extension: {extension}. Skipping file.")
        return None

def process_file(file_path_before, file_path_after, repo_path):
    extension = os.path.splitext(file_path_before)[1]
    handler = get_handler_for_extension(extension)
    if handler is None:
        return [], []  # Return empty lists for modified and called functions

    #print(f"Processing {file_path_before} and {file_path_after} with {handler.__class__.__name__}")

    # Read the previous version of the code
    source_code_before = read_file(file_path_before)
    funcs_before = handler.extract_functions(source_code_before)

    # If `current_repo` does not contain this file, all functions in `previous_repo` are considered deleted
    if not os.path.exists(file_path_after):
        print(f"After file does not exist, considering all functions as deleted.")
        modified_funcs = [f"{file_path_before}/{sig}" for sig in funcs_before.keys()]
        return modified_funcs, []

    # Read the current version of the code
    source_code_after = read_file(file_path_after)
    funcs_after = handler.extract_functions(source_code_after)

    modified_funcs = []
    modified_called_funcs = set()  # Use a set to avoid duplicates

    # Compare functions in `previous_repo` and `current_repo`
    for func_signature, func_data in funcs_before.items():
        if func_signature not in funcs_after:
            # If the function does not exist in `current_repo`, it is considered deleted
            modified_funcs.append(f"{file_path_before}/{func_signature}")
            print(f"Deleted function: {file_path_before}/{func_signature}")
        else:
            # Process modified functions when code has changed
            if handler.compare_functions({func_signature: func_data}, {func_signature: funcs_after[func_signature]}):
                full_function_path = f"{file_path_before}/{func_signature}"
                modified_funcs.append(full_function_path)
                print(f"Modified function: {full_function_path}")

                # Retrieve called functions
                func_node_before = funcs_before.get(func_signature, {}).get("node")
                func_node_after = funcs_after.get(func_signature, {}).get("node")

                if func_node_before and func_node_after:
                    called_funcs_before = handler.find_called_functions(func_node_before)
                    called_funcs_after = handler.find_called_functions(func_node_after)

                    for called_func_before in called_funcs_before:
                        if called_func_before not in called_funcs_after:
                            implementations = handler.find_function_implementation(repo_path, called_func_before)
                            if implementations:
                                for filepath, func_signature, _ in implementations:
                                    unique_signature = f"{filepath}/{func_signature}"
                                    modified_called_funcs.add(unique_signature.strip())

    return modified_funcs, list(modified_called_funcs)  # Return modified functions and called functions

def read_file(file_path):
    #print(f"Reading file: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def generate_candidate_list():
    base_dir = os.getcwd()
    previous_repo_path = os.path.join(base_dir, "previous_repo")
    current_repo_path = os.path.join(base_dir, "current_repo")

    if not os.path.exists(previous_repo_path) or not os.path.exists(current_repo_path):
        #print("Error: Both previous_repo and current_repo folders must exist.")
        return ""

    all_modified_funcs = []
    all_modified_called_funcs = []

    for root, _, files in os.walk(previous_repo_path):
        for filename in files:
            relative_path = os.path.relpath(root, previous_repo_path)
            file_path_before = os.path.join(previous_repo_path, relative_path, filename)
            file_path_after = os.path.join(current_repo_path, relative_path, filename)

            modified_funcs, modified_called_funcs = process_file(file_path_before, file_path_after, previous_repo_path)

            # Remove the `previous_repo` prefix and keep only the relative path
            modified_funcs = [func.replace(f"{previous_repo_path}\\", "") for func in modified_funcs]
            modified_called_funcs = [func.replace(f"{previous_repo_path}\\", "") for func in modified_called_funcs]

            all_modified_funcs.extend(modified_funcs)
            all_modified_called_funcs.extend(modified_called_funcs)

    final_report = "Modified Functions:\n"
    final_report += "\n".join([f"  {i+1}. {func}" for i, func in enumerate(all_modified_funcs)]) + "\n"
    final_report += "Modified Called Functions:\n"
    final_report += "\n".join([f"  {i+1}. {func}" for i, func in enumerate(set(all_modified_called_funcs))]) + "\n"

    return final_report
