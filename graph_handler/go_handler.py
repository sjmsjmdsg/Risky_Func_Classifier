# gohandler.py

import os
import networkx as nx
from tree_sitter import Language, Parser
import chardet
import tree_sitter_go as ts_go
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Tree-sitter setup
GO_LANGUAGE = Language(ts_go.language())
parser = Parser()
parser.language = GO_LANGUAGE


class GoHandler:
    def __init__(self):
        # Initialize the parser
        self.language = GO_LANGUAGE
        self.parser = Parser()
        self.parser.language = self.language
        self.defined_functions = set()  # Set of defined functions
        self.call_graph = nx.DiGraph()
        self.matched_functions = []  # List of matched target functions
        self.distances = {}
        self.function_calls = {}  # Function call relationships, key: caller function, value: set of called functions
        self.common_called_functions = set()  # Commonly called external functions

    # Parse a single file and build call relationships
    def parse_file(self, file_path):
        if os.path.exists(file_path):
            code = self.read_file_with_detected_encoding(file_path)
            tree = self.parser.parse(bytes(code, 'utf8'))
            root_node = tree.root_node
            # Collect functions defined in the file
            self.collect_defined_functions(root_node)
            # Collect function call relationships
            self.collect_calls(root_node)
        else:
            print(f"File {file_path} does not exist!")

    # Automatically detect file encoding and read file content
    def read_file_with_detected_encoding(self, file_path):
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding']

        # Fall back to utf-8 if the detected encoding is unknown
        if encoding is None or encoding.lower() not in ["utf-8", "ascii"]:
            print(f"Unknown or unsupported encoding {encoding} for file {file_path}, using utf-8 with errors='replace'")
            encoding = 'utf-8'

        try:
            # Read the file using the detected encoding
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                return f.read()
        except (UnicodeDecodeError, LookupError) as e:
            # If the detected encoding is not available or decoding fails, use utf-8 and ignore errors
            print(f"Failed to decode {file_path} using {encoding}, trying utf-8 with errors='ignore'")
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

    # Collect all function names defined in the file
    def collect_defined_functions(self, root_node):
        cursor = root_node.walk()
        reached_root = False
        while not reached_root:
            node = cursor.node

            if node.type in ('function_declaration', 'method_declaration'):
                func_name = self.get_full_function_name(node)
                if func_name:
                    self.defined_functions.add(func_name)
            if cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                continue
            while True:
                if not cursor.goto_parent():
                    reached_root = True
                    break
                if cursor.goto_next_sibling():
                    break

    # Get the full function name, in the format "receiver_type.func_name" or "func_name"
    def get_full_function_name(self, node):
        func_name_node = node.child_by_field_name('name')
        if func_name_node:
            func_name = func_name_node.text.decode('utf8')

            # If it's a method, get the receiver type
            receiver_node = node.child_by_field_name('receiver')
            if receiver_node:
                # Further parse the receiver type
                receiver_type_node = receiver_node.named_child(0)
                if receiver_type_node:
                    receiver_type = receiver_type_node.text.decode('utf8')
                    func_full_name = f"{receiver_type}.{func_name}"
                else:
                    func_full_name = func_name  # Use function name if receiver type is not available
            else:
                func_full_name = func_name

            return func_full_name
        else:
            print("Function declaration without a name.")
            return None

    # Collect function call relationships
    def collect_calls(self, root_node):
        cursor = root_node.walk()
        reached_root = False
        while not reached_root:
            node = cursor.node
            if node.type in ('function_declaration', 'method_declaration'):
                caller_func = self.get_full_function_name(node)
                if caller_func:
                    # Traverse the function body to collect call relationships
                    func_body_node = node.child_by_field_name('body')
                    if func_body_node:
                        self._collect_calls_in_body(caller_func, func_body_node)
            if cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                continue
            while True:
                if not cursor.goto_parent():
                    reached_root = True
                    break
                if cursor.goto_next_sibling():
                    break

    # Collect call relationships within the function body
    def _collect_calls_in_body(self, caller_func, node):
        if node.type == 'call_expression':
            function_node = node.child_by_field_name('function')
            if function_node:
                called_func_name = self.get_called_function_name(function_node)
                if called_func_name:
                    if caller_func not in self.function_calls:
                        self.function_calls[caller_func] = set()
                    self.function_calls[caller_func].add(called_func_name)
                    # Add an edge only if the called function is in the set of defined functions
                    if called_func_name in self.defined_functions:
                        self.call_graph.add_edge(caller_func, called_func_name)
        for child in node.children:
            self._collect_calls_in_body(caller_func, child)

    # Get the name of the called function
    def get_called_function_name(self, function_node):
        if function_node.type == 'identifier':
            return function_node.text.decode('utf8')
        elif function_node.type == 'selector_expression':
            operand_node = function_node.child_by_field_name('operand')
            field_node = function_node.child_by_field_name('field')
            if operand_node and field_node:
                operand = operand_node.text.decode('utf8')
                field = field_node.text.decode('utf8')
                called_func_name = f"{operand}.{field}"
                return called_func_name
        else:
            # Other types may require further handling
            return function_node.text.decode('utf8')
        return None

    # Match target functions (ignoring receiver type and parameters)
    def match_target_functions(self, target_functions):
        self.matched_functions = []
        for func in self.defined_functions:
            func_name = func.split('.')[-1]  # Extract function name without receiver
            for target_func in target_functions:
                if func_name == target_func:
                    self.matched_functions.append(func)
                    break

    # Find all external functions commonly called by target functions
    def find_common_called_functions(self):
        # Get the set of functions called by each target function
        target_called_functions = []
        for func in self.matched_functions:
            called_funcs = self.function_calls.get(func, set())
            # Filter out defined functions, keeping only external ones
            external_called_funcs = {func_name for func_name in called_funcs if func_name not in self.defined_functions}
            target_called_functions.append(external_called_funcs)
        # Find the common external functions
        if target_called_functions:
            common_called_funcs = set.intersection(*target_called_functions)
            self.common_called_functions = common_called_funcs
            # Add these external functions to the call graph
            for func in self.common_called_functions:
                self.call_graph.add_node(func)
                for caller_func in self.matched_functions:
                    if func in self.function_calls.get(caller_func, set()):
                        self.call_graph.add_edge(caller_func, func)
        else:
            self.common_called_functions = set()

    # Compute shortest path distances between target functions (in an undirected graph)
    def compute_distances(self):
        self.distances = {}
        undirected_graph = self.call_graph.to_undirected()
        for i, func1 in enumerate(self.matched_functions):
            for func2 in self.matched_functions[i + 1:]:
                try:
                    distance = nx.shortest_path_length(undirected_graph, source=func1, target=func2)
                    self.distances[(func1, func2)] = distance
                except nx.NetworkXNoPath:
                    self.distances[(func1, func2)] = None

    # Draw the call graph
    def draw_call_graph(self, output_path):
        plt.figure(figsize=(12, 8))  # Set graph size
        pos = nx.spring_layout(self.call_graph, k=0.5, iterations=50)  # Compute node positions

        # Create a list of node colors to distinguish different types of nodes
        node_colors = []
        for node in self.call_graph.nodes():
            if node in self.matched_functions:
                node_colors.append('red')  # Target nodes in red
            elif node in self.common_called_functions:
                node_colors.append('green')  # Commonly called external functions in green
            else:
                node_colors.append('lightblue')  # Other defined functions in light blue
        # Draw nodes
        nx.draw_networkx_nodes(self.call_graph, pos, node_color=node_colors, node_size=500)
        # Draw edges
        nx.draw_networkx_edges(self.call_graph, pos, arrows=True)
        # Draw node labels
        nx.draw_networkx_labels(self.call_graph, pos, font_size=8)


