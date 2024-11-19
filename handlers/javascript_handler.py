from tree_sitter import Language, Parser
import tree_sitter_javascript as ts_javascript
from .base_handlers import LanguageHandler
import os

class JavaScriptHandler(LanguageHandler):
    def __init__(self):
        # Initialize JavaScript parser
        JAVASCRIPT_LANGUAGE = Language(ts_javascript.language())
        parser = Parser()
        parser.language = JAVASCRIPT_LANGUAGE  # Set language to JavaScript
        super().__init__(parser=parser)

    def read_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def extract_functions(self, source_code):
        tree = self.parser.parse(source_code.encode('utf-8'))
        root_node = tree.root_node

        functions = {}

        def walk(node, class_name=None):
            if node.type == 'class_declaration':
                # Handle class declaration
                class_name_node = node.child_by_field_name('name')
                if class_name_node:
                    class_name = class_name_node.text.decode('utf-8')

            if node.type == 'method_definition' or node.type == 'function_declaration':
                # Handle function or method declaration
                func_name_node = node.child_by_field_name('name')
                parameters_node = node.child_by_field_name('parameters')

                if func_name_node and parameters_node:
                    func_name = func_name_node.text.decode('utf-8')
                    parameters = parameters_node.text.decode('utf-8')
                    if class_name:
                        func_signature = f"{class_name}/{func_name}{parameters}"
                    else:
                        func_signature = f"{func_name}{parameters}"

                    func_start = node.start_point[0]
                    func_end = node.end_point[0]
                    func_code = source_code.splitlines()[func_start:func_end + 1]
                    functions[func_signature] = {
                        "code": "\n".join(func_code).strip(),
                        "node": node  # Save node for later analysis
                    }

            for child in node.children:
                walk(child, class_name)

        walk(root_node)
        return functions

    def compare_functions(self, funcs_before, funcs_after):
        # Compare functions between two versions and return modified functions
        modified_funcs = []

        for func_signature, func_data in funcs_before.items():
            if func_signature not in funcs_after or funcs_after[func_signature]["code"] != func_data["code"]:
                modified_funcs.append(func_signature)

        return modified_funcs

    def find_called_functions(self, func_node):
        # Find all functions called within a given function
        called_functions = []

        def walk(node):
            if node.type == 'call_expression':
                func_node = node.child_by_field_name('function')
                if func_node:
                    called_func_name = func_node.text.decode('utf-8').split('.')[-1]  # Remove prefixes
                    called_functions.append(called_func_name)

            for child in node.children:
                walk(child)

        walk(func_node)
        return called_functions

    def find_function_implementation(self, repo_path, function_signature):
        # Search the entire repo for the function's definition and implementation
        function_implementations = []
        function_name = function_signature.split('(')[0]  # Extract function name, remove parameters
        function_name = function_name.split('/')[-1]  # Remove class name if present

        for dirpath, _, filenames in os.walk(repo_path):
            for filename in filenames:
                if filename.endswith(".js"):  # Only search JavaScript files
                    file_path = os.path.join(dirpath, filename)
                    source_code = self.read_file(file_path)
                    tree = self.parser.parse(source_code.encode('utf-8'))
                    root_node = tree.root_node

                    def walk(node, class_name=None):
                        if node.type == 'class_declaration':
                            # Handle class declaration
                            class_name_node = node.child_by_field_name('name')
                            if class_name_node:
                                class_name = class_name_node.text.decode('utf-8')

                        if node.type == 'method_definition' or node.type == 'function_declaration':
                            func_name_node = node.child_by_field_name('name')
                            parameters_node = node.child_by_field_name('parameters')
                            if func_name_node and func_name_node.text.decode('utf-8') == function_name:
                                parameters = parameters_node.text.decode('utf-8') if parameters_node else "()"
                                if class_name:
                                    full_signature = f"{class_name}/{function_name}{parameters}"
                                else:
                                    full_signature = f"{function_name}{parameters}"

                                func_start = node.start_point[0]
                                func_end = node.end_point[0]
                                func_code = source_code.splitlines()[func_start:func_end + 1]
                                function_implementations.append(
                                    (file_path, full_signature, "\n".join(func_code).strip()))

                        for child in node.children:
                            walk(child, class_name)

                    walk(root_node)
        return function_implementations
