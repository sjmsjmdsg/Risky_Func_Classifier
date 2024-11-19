from tree_sitter import Language, Parser
import tree_sitter_c as ts_c
from .base_handlers import LanguageHandler
import os
import re  # Import the regular expression module

class CHandler(LanguageHandler):
    def __init__(self):
        # Initialize the parser for C language
        C_LANGUAGE = Language(ts_c.language())
        parser = Parser()
        parser.language = C_LANGUAGE  # Set the language
        super().__init__(parser=parser)

    def read_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def extract_functions(self, source_code):
        tree = self.parser.parse(source_code.encode('utf-8'))
        root_node = tree.root_node

        functions = {}

        def walk(node, depth=0):
            if depth > 100:  # Limit recursion depth to 100
                return

            if node.type == 'function_definition':
                # Handle function definitions
                func_name_node = node.child_by_field_name('declarator')
                func_signature, func_code = self.process_function_node(node, func_name_node, source_code)
                if func_signature:
                    functions[func_signature] = {
                        "code": func_code,
                        "node": node  # Save the node for further analysis of called functions
                    }

            elif node.type == 'declaration':
                # Handle function declarations (without a body)
                type_node = node.child_by_field_name('type')
                declarator_node = node.child_by_field_name('declarator')
                # Check if it's a function declaration
                if declarator_node and self.is_function_declarator(declarator_node):
                    func_signature, func_code = self.process_function_node(node, declarator_node, source_code)
                    if func_signature:
                        functions[func_signature] = {
                            "code": func_code,
                            "node": node
                        }

            elif node.type == 'preproc_function_def':
                # Handle preprocessor function definitions
                func_name_node = node.child_by_field_name('name')
                parameters_node = node.child_by_field_name('parameters')
                func_name = func_name_node.text.decode('utf-8') if func_name_node else None
                parameters = parameters_node.text.decode('utf-8') if parameters_node else "()"
                func_signature = f"{func_name}{parameters}"
                func_start = node.start_point[0]
                func_end = node.end_point[0]
                func_code = source_code.splitlines()[func_start:func_end + 1]
                if func_name:
                    functions[func_signature] = {
                        "code": "\n".join(func_code).strip(),
                        "node": node
                    }

            # Recursively traverse child nodes
            for child in node.children:
                walk(child, depth + 1)  # Increase recursion depth

        walk(root_node)
        return functions

    def is_function_declarator(self, node):
        # Check if the declarator represents a function
        if node.type == 'function_declarator':
            return True
        # Handle pointer cases
        child = node.child_by_field_name('declarator')
        if child:
            return self.is_function_declarator(child)
        return False

    def process_function_node(self, node, func_name_node, source_code):
        if func_name_node:
            # Handle pointers and references
            pointer_node = func_name_node.child_by_field_name('declarator')
            parameters_node = func_name_node.child_by_field_name('parameters')

            # Ensure child nodes exist
            if pointer_node:
                func_name = pointer_node.text.decode('utf-8')
            elif func_name_node:
                func_name = func_name_node.text.decode('utf-8')
            else:
                func_name = None

            if func_name:
                parameters = parameters_node.text.decode('utf-8') if parameters_node else "()"
                func_signature = f"{func_name}{parameters}"

                func_start = node.start_point[0]
                func_end = node.end_point[0]
                func_code = source_code.splitlines()[func_start:func_end + 1]
                func_code_str = "\n".join(func_code).strip()
                return func_signature, func_code_str
        return None, None

    def remove_comments_whitespace(self, code):
        # Remove comments (supports single-line and multi-line comments)
        code = re.sub(r'//.*?$|/\*.*?\*/', '', code, flags=re.DOTALL | re.MULTILINE)
        # Remove empty lines, extra spaces, and tabs
        code = re.sub(r'\s+', '', code)  # \s includes spaces, newlines, and tabs
        return code

    def compare_functions(self, funcs_before, funcs_after):
        # Compare function lists in two versions and return modified function signatures
        modified_funcs = []

        for func_signature, func_data in funcs_before.items():
            # Preprocess function code to remove comments, empty lines, tabs, and extra spaces
            code_before = self.remove_comments_whitespace(func_data["code"])
            if func_signature not in funcs_after:
                modified_funcs.append(func_signature)
                continue
            code_after = self.remove_comments_whitespace(funcs_after[func_signature]["code"])

            # Compare the preprocessed code
            if code_before != code_after:
                modified_funcs.append(func_signature)

        return modified_funcs

    def find_called_functions(self, func_node):
        # Find all functions called within a function along with their arguments
        called_functions = []

        def walk(node, depth=0):
            if depth > 100:  # Limit recursion depth to 100
                return

            if node.type == 'call_expression':
                func_node = node.child_by_field_name('function')
                if func_node:
                    called_func_name = func_node.text.decode('utf-8')
                    called_functions.append(called_func_name)

            for child in node.children:
                walk(child, depth + 1)

        walk(func_node)
        return called_functions

    def find_function_implementation(self, repo_path, function_signature):
        # Search for function definitions and implementations across the repository
        function_implementations = []
        function_name = function_signature.split('(')[0]  # Remove parameters to extract the function name
        for dirpath, _, filenames in os.walk(repo_path):
            for filename in filenames:
                if filename.endswith(".c") or filename.endswith(".h"):  # Only search in C and header files
                    file_path = os.path.join(dirpath, filename)
                    source_code = self.read_file(file_path)
                    tree = self.parser.parse(source_code.encode('utf-8'))
                    root_node = tree.root_node

                    def walk(node, depth=0):
                        if depth > 100:  # Limit recursion depth to 100
                            return

                        if node.type == 'function_definition':
                            func_name_node = node.child_by_field_name('declarator')
                            pointer_node = func_name_node.child_by_field_name('declarator') if func_name_node else None
                            parameters_node = func_name_node.child_by_field_name('parameters') if func_name_node else None

                            if func_name_node and ((pointer_node and pointer_node.text.decode('utf-8') == function_name) or func_name_node.text.decode('utf-8') == function_name):
                                func_name = pointer_node.text.decode('utf-8') if pointer_node else func_name_node.text.decode('utf-8')
                                parameters = parameters_node.text.decode('utf-8') if parameters_node else "()"
                                full_signature = f"{func_name}{parameters}"

                                func_start = node.start_point[0]
                                func_end = node.end_point[0]
                                func_code = source_code.splitlines()[func_start:func_end + 1]
                                function_implementations.append(
                                    (file_path, full_signature, "\n".join(func_code).strip())
                                )

                        # Handle function declarations
                        elif node.type == 'declaration':
                            declarator_node = node.child_by_field_name('declarator')
                            if declarator_node and self.is_function_declarator(declarator_node):
                                func_name_node = declarator_node.child_by_field_name('declarator')
                                parameters_node = declarator_node.child_by_field_name('parameters')

                                if func_name_node and ((func_name_node.text.decode('utf-8') == function_name) or (func_name_node.child_by_field_name('declarator') and func_name_node.child_by_field_name('declarator').text.decode('utf-8') == function_name)):
                                    func_name = func_name_node.text.decode('utf-8')
                                    parameters = parameters_node.text.decode('utf-8') if parameters_node else "()"
                                    full_signature = f"{func_name}{parameters}"

                                    func_start = node.start_point[0]
                                    func_end = node.end_point[0]
                                    func_code = source_code.splitlines()[func_start:func_end + 1]
                                    function_implementations.append(
                                        (file_path, full_signature, "\n".join(func_code).strip())
                                    )

                        for child in node.children:
                            walk(child, depth + 1)

                    walk(root_node)
        return function_implementations
