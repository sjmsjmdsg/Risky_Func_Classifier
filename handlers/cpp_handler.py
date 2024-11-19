from tree_sitter import Language, Parser
import tree_sitter_cpp as ts_cpp
from .base_handlers import LanguageHandler
import os
import re

class CppHandler(LanguageHandler):
    def __init__(self):
        # Initialize the parser for C++ language
        CPP_LANGUAGE = Language(ts_cpp.language())
        parser = Parser()
        parser.language = CPP_LANGUAGE  # Set the language
        super().__init__(parser=parser)

    def read_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def extract_functions(self, source_code):
        tree = self.parser.parse(bytes(source_code, 'utf8'))
        root_node = tree.root_node

        functions = {}

        def walk(node, class_name=None, depth=0):
            if depth > 100:  # Limit recursion depth
                return

            if node.type == 'class_specifier':
                # Handle class definitions
                class_name_node = node.child_by_field_name('name')
                if class_name_node:
                    current_class_name = self.get_node_text(class_name_node, source_code)
                else:
                    current_class_name = class_name  # If no class name, retain the parent class name

                # Recursively handle the contents of the class
                body_node = node.child_by_field_name('body')
                if body_node:
                    for child in body_node.children:
                        walk(child, current_class_name, depth + 1)

            elif node.type in ['function_definition', 'constructor_definition', 'destructor_definition']:
                # Handle functions, constructors, and destructors
                func_name_node = node.child_by_field_name('declarator') or node.child_by_field_name('name')
                parameters_node = node.child_by_field_name('parameters')

                if func_name_node:
                    func_name = self.get_node_text(func_name_node, source_code)
                    parameters = self.get_node_text(parameters_node, source_code) if parameters_node else "()"
                    if class_name:
                        func_signature = f"{class_name}/{func_name}{parameters}"
                    else:
                        func_signature = f"{func_name}{parameters}"

                    func_start = node.start_point[0]
                    func_end = node.end_point[0]
                    func_code_lines = source_code.splitlines()[func_start:func_end + 1]
                    func_code = "\n".join(func_code_lines).strip()

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

    def get_node_text(self, node, source_code):
        if node:  # Check if node is not None
            return source_code[node.start_byte:node.end_byte]
        return ""

    def remove_comments_whitespace(self, code):
        # Remove single-line comments (// comments)
        code = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
        # Remove multi-line comments (/* ... */)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        # Remove whitespace characters (including spaces, newlines, and tabs)
        code = re.sub(r'\s+', '', code)
        return code

    def compare_functions(self, funcs_before, funcs_after):
        # Compare function lists in two versions and return modified function signatures
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
        # Find all functions called within a function
        called_functions = []

        def walk(node, depth=0):
            if depth > 100:
                return

            if node.type == 'call_expression':
                # Get the name of the called function
                function_node = node.child_by_field_name('function')
                if function_node:
                    called_func_name = self.get_full_name(function_node)
                    called_functions.append(called_func_name)

            # Recursively traverse child nodes
            for child in node.children:
                walk(child, depth + 1)

        walk(func_node)
        return called_functions

    def get_full_name(self, node):
        if node is None:
            return ""  # Check if node is None

        # Get the full function name, handle class methods and static method calls
        if node.type == 'identifier':
            return node.text.decode('utf-8')
        elif node.type == 'field_expression':
            obj_node = node.child_by_field_name('object')
            field_node = node.child_by_field_name('field')

            # Check if obj_node and field_node are None
            obj = self.get_full_name(obj_node) if obj_node else ''
            field = self.get_full_name(field_node) if field_node else ''
            return f"{obj}->{field}" if obj and field else field
        else:
            return node.text.decode('utf-8')

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
                if filename.endswith((".cpp", ".hpp", ".h", ".cxx", ".cc")):  # Only search in C++ files
                    file_path = os.path.join(dirpath, filename)
                    source_code = self.read_file(file_path)
                    tree = self.parser.parse(bytes(source_code, 'utf8'))
                    root_node = tree.root_node

                    def walk(node, current_class_name=None, depth=0):
                        if depth > 100:
                            return

                        if node.type == 'class_specifier':
                            # Handle class definitions
                            class_name_node = node.child_by_field_name('name')
                            if class_name_node:
                                new_class_name = self.get_node_text(class_name_node, source_code)
                            else:
                                new_class_name = current_class_name

                            # Recursively handle the contents of the class
                            body_node = node.child_by_field_name('body')
                            if body_node:
                                for child in body_node.children:
                                    walk(child, new_class_name, depth + 1)

                        elif node.type in ['function_definition', 'constructor_definition', 'destructor_definition']:
                            func_name_node = node.child_by_field_name('declarator') or node.child_by_field_name('name')
                            if func_name_node:
                                func_name = self.get_node_text(func_name_node, source_code)
                                if func_name == function_name:
                                    # If a class name is specified, check if it matches
                                    if class_name and current_class_name != class_name:
                                        return
                                    func_start = node.start_point[0]
                                    func_end = node.end_point[0]
                                    func_code_lines = source_code.splitlines()[func_start:func_end + 1]
                                    func_code = "\n".join(func_code_lines).strip()
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
