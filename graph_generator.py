import os
import re
import networkx as nx
from graph_handler.go_handler import GoHandler
from graph_handler.c_handler import CHandler

def parse_modified_functions(candidate_str):
    functions = []
    # Use regex to extract content between 'Modified Functions:' and 'Modified Called Functions:'
    pattern = r'Modified Functions:\s*(.*?)\s*Modified Called Functions:'
    match = re.search(pattern, candidate_str, re.DOTALL)
    if match:
        modified_functions_text = match.group(1)
        for line in modified_functions_text.strip().split('\n'):
            line = line.strip()
            if line:
                match_line = re.match(r'\d+\.\s+(.*)', line)
                if match_line:
                    func_info = match_line.group(1)
                    func_parts = func_info.strip().split('/')
                    if len(func_parts) >= 2:
                        file_path_parts = func_parts[:-1]
                        func_name_with_signature = func_parts[-1]
                        func_name = func_name_with_signature.split('(')[0]
                        file_path = os.path.join(*file_path_parts)
                        functions.append((func_name, file_path))
    else:
        print("No 'Modified Functions' section found in the candidate text.")
    return functions

def generate_call_graph_dot(candidate_str, base_dir):
    handlers = {
        '.go': GoHandler(),
        '.c': CHandler()
    }

    target_functions_with_paths = parse_modified_functions(candidate_str)
    if not target_functions_with_paths:
        print("No target functions extracted from candidate input.")
        return ""

    # Use NetworkX to create a directed graph
    G = nx.DiGraph()

    # Iterate over target files and build the call graph
    for func_name, relative_file_path in target_functions_with_paths:
        file_path = os.path.join(base_dir, "previous_repo", relative_file_path)
        if not os.path.exists(file_path):
            print(f"File {file_path} does not exist. Skipping.")
            continue

        ext = os.path.splitext(file_path)[1]
        handler = handlers.get(ext)
        if handler:
            handler.parse_file(file_path)
            handler.match_target_functions([func_name])  # Match target functions

            if func_name in handler.function_calls:
                G.add_node(func_name)
                for called_func in handler.function_calls[func_name]:
                    G.add_node(called_func)
                    G.add_edge(func_name, called_func)
            else:
                print(f"Function {func_name} not found in defined functions.")
        else:
            print(f"No handler for file extension {ext}")

    # Generate the call graph in DOT format
    dot_output = "digraph CallGraph {\n"
    for func in G.nodes:
        dot_output += f'  "{func}";\n'
    for caller, callee in G.edges:
        dot_output += f'  "{caller}" -> "{callee}";\n'
    dot_output += "}\n"

    return dot_output
