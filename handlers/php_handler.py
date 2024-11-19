from tree_sitter import Language, Parser
import tree_sitter_php as ts_php
from .base_handlers import LanguageHandler
import os
import re

class PhpHandler(LanguageHandler):
    def __init__(self):
        # Initialize the PHP language parser
        PHP_LANGUAGE = Language(ts_php.language_php())
        parser = Parser()
        parser.language = PHP_LANGUAGE  # Set the language
        super().__init__(parser=parser)

    def extract_functions(self, source_code):
        # Check if source_code is a string; if so, encode it as bytes
        if isinstance(source_code, str):
            source_bytes = source_code.encode('utf-8')
        else:
            source_bytes = source_code  # Already in bytes

        tree = self.parser.parse(source_bytes)
        root_node = tree.root_node

        functions = {}

        def walk(node, class_name=None, depth=0):
            if depth > 100:  # Limit recursion depth
                return

            if node.type == 'class_declaration':
                # Handle class declarations
                class_name_node = node.child_by_field_name('name')
                if class_name_node:
                    current_class_name = self.get_node_text(class_name_node, source_bytes)
                else:
                    current_class_name = class_name  # If no class name, retain the parent class name

                # Recursively process the content inside the class
                body_node = node.child_by_field_name('body')
                if body_node:
                    for child in body_node.children:
                        walk(child, current_class_name, depth + 1)

            elif node.type in ['method_declaration', 'function_definition', 'function_declaration']:
                # Handle method and function definitions
                func_name_node = node.child_by_field_name('name')
                parameters_node = node.child_by_field_name('parameters')

                if func_name_node:
                    func_name = self.get_node_text(func_name_node, source_bytes)
                    parameters = self.get_node_text(parameters_node, source_bytes) if parameters_node else "()"
                    if class_name:
                        func_signature = f"{class_name}/{func_name}{parameters}"
                    else:
                        func_signature = f"{func_name}{parameters}"

                    # Retrieve the function code
                    func_code = self.get_node_text(node, source_bytes).strip()

                    functions[func_signature] = {
                        "code": func_code,
                        "node": node  # Save the node for further analysis of called functions
                    }

                # Recursively traverse the function body (if necessary)
                body_node = node.child_by_field_name('body')
                if body_node:
                    for child in body_node.children:
                        walk(child, class_name, depth + 1)

            else:
                # Recursively traverse other nodes
                for child in node.children:
                    walk(child, class_name, depth + 1)

        walk(root_node)
        return functions

    def get_node_text(self, node, source_bytes):
        # Get the source code text corresponding to a node and decode it as a string
        return source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

    def remove_comments_whitespace(self, code):
        # Remove single-line comments (// and # comments)
        code = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
        code = re.sub(r'#.*?$', '', code, flags=re.MULTILINE)
        # Remove multi-line comments (/* ... */)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        # Remove whitespace characters (including spaces, newlines, and tabs)
        code = re.sub(r'\s+', '', code)
        return code

    def compare_functions(self, funcs_before, funcs_after):
        # Compare function lists between two versions and return modified function signatures
        modified_funcs = []

        for func_signature, func_data in funcs_before.items():
            if func_signature not in funcs_after:
                modified_funcs.append(func_signature)
                continue

            code_before = self.remove_comments_whitespace(func_data["code"])
            code_after = self.remove_comments_whitespace(funcs_after[func_signature]["code"])

            if code_before != code_after:
                modified_funcs.append(func_signature)

        return modified_funcs

    def find_called_functions(self, func_node):
        # Identify all functions called within a function
        called_functions = []

        def walk(node, depth=0):
            if depth > 100:
                return

            if node.type in ['function_call_expression', 'member_call_expression']:
                # Get the name of the called function
                function_node = node.child_by_field_name('callable')
                if function_node:
                    called_func_name = self.get_full_name(function_node)
                    called_functions.append(called_func_name)

            # Recursively traverse child nodes
            for child in node.children:
                walk(child, depth + 1)

        walk(func_node)
        return called_functions

    def get_full_name(self, node):
        # Retrieve the full function name, handling method calls and static method calls
        if node.type == 'name':
            return self.get_node_text(node, node.tree.source_code)
        elif node.type in ['member_call_expression', 'scoped_call_expression']:
            receiver_node = node.child_by_field_name('object') or node.child_by_field_name('scope')
            method_node = node.child_by_field_name('name')
            receiver = self.get_full_name(receiver_node) if receiver_node else ''
            method = self.get_node_text(method_node, node.tree.source_code) if method_node else ''
            if receiver and method:
                return f"{receiver}->{method}"
            else:
                return method
        else:
            return self.get_node_text(node, node.tree.source_code)

    def find_function_implementation(self, repo_path, function_signature):
        # Search for function definitions and implementations across the repository
        function_implementations = []
        # Extract function name and class name
        if '/' in function_signature:
            class_name, func_part = function_signature.split('/', 1)
        else:
            class_name = None
            func_part = function_signature

        function_name = func_part.split('(')[0]  # Remove parameters to extract the function name

        for dirpath, _, filenames in os.walk(repo_path):
            for filename in filenames:
                if filename.endswith(".php"):  # Only search in PHP files
                    file_path = os.path.join(dirpath, filename)
                    source_code = self.read_file(file_path)
                    if isinstance(source_code, str):
                        source_bytes = source_code.encode('utf-8')
                    else:
                        source_bytes = source_code

                    tree = self.parser.parse(source_bytes)
                    root_node = tree.root_node

                    def walk(node, current_class_name=None, depth=0):
                        if depth > 100:
                            return

                        if node.type == 'class_declaration':
                            # Handle class declarations
                            class_name_node = node.child_by_field_name('name')
                            if class_name_node:
                                new_class_name = self.get_node_text(class_name_node, source_bytes)
                            else:
                                new_class_name = current_class_name

                            # Recursively process the content inside the class
                            body_node = node.child_by_field_name('body')
                            if body_node:
                                for child in body_node.children:
                                    walk(child, new_class_name, depth + 1)

                        elif node.type in ['method_declaration', 'function_definition', 'function_declaration']:
                            func_name_node = node.child_by_field_name('name')
                            if func_name_node:
                                func_name = self.get_node_text(func_name_node, source_bytes)
                                if func_name == function_name:
                                    # If a class name is specified, check if it matches
                                    if class_name and current_class_name != class_name:
                                        return
                                    func_code = self.get_node_text(node, source_bytes).strip()
                                    if current_class_name:
                                        full_signature = f"{current_class_name}/{func_name}"
                                    else:
                                        full_signature = func_name
                                    function_implementations.append(
                                        (file_path, full_signature, func_code)
                                    )
                            # Recursively traverse the function body (if necessary)
                            body_node = node.child_by_field_name('body')
                            if body_node:
                                for child in body_node.children:
                                    walk(child, current_class_name, depth + 1)
                        else:
                            # Recursively traverse other nodes
                            for child in node.children:
                                walk(child, current_class_name, depth + 1)

                    walk(root_node)

        return function_implementations
