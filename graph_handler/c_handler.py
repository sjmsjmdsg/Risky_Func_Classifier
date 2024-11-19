import os
import networkx as nx
from tree_sitter import Language, Parser
import chardet
import tree_sitter_c as ts_c
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Tree-sitter 设置
C_LANGUAGE = Language(ts_c.language())
parser = Parser()
parser.language = C_LANGUAGE

class CHandler:
    def __init__(self):
        # 初始化解析器
        self.language = C_LANGUAGE
        self.parser = Parser()
        self.parser.language = self.language
        self.defined_functions = set()      # Set of defined functions
        self.call_graph = nx.DiGraph()
        self.matched_functions = []         # List of matched target functions
        self.distances = {}
        self.function_calls = {}            # Function call relationships, key: caller function, value: set of called functions
        self.common_called_functions = set()  # Commonly called external functions

    # Parse a single file to build function call relationships
    def parse_file(self, file_path):
        if os.path.exists(file_path):
            code = self.read_file_with_detected_encoding(file_path)
            tree = self.parser.parse(bytes(code, 'utf8'))
            root_node = tree.root_node
            # Collect defined functions in the file
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

        if encoding is None or encoding.lower() not in ["utf-8", "ascii"]:
            print(f"Unknown or unsupported encoding {encoding} for file {file_path}, using utf-8 with errors='replace'")
            encoding = 'utf-8'

        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                return f.read()
        except (UnicodeDecodeError, LookupError) as e:
            print(f"Failed to decode {file_path} using {encoding}, trying utf-8 with errors='ignore'")
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

    # Collect all function names defined in the file
    def collect_defined_functions(self, root_node):
        cursor = root_node.walk()
        reached_root = False
        while not reached_root:
            node = cursor.node
            if node.type == 'function_definition':
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

    # Get the full function name
    def get_full_function_name(self, node):
        declarator_node = node.child_by_field_name('declarator')
        if declarator_node:
            func_name_node = declarator_node.child_by_field_name('declarator')
            if func_name_node:
                func_name = func_name_node.text.decode('utf8')
                return func_name
        else:
            print("Function definition without a name.")
            return None

    # Collect function call relationships
    def collect_calls(self, root_node):
        cursor = root_node.walk()
        reached_root = False
        while not reached_root:
            node = cursor.node
            if node.type == 'function_definition':
                caller_func = self.get_full_function_name(node)
                if caller_func:
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

    # Collect call relationships within a function body
    def _collect_calls_in_body(self, caller_func, node):
        if node.type == 'call_expression':
            function_node = node.child_by_field_name('function')
            if function_node:
                called_func_name = self.get_called_function_name(function_node)
                if called_func_name:
                    if caller_func not in self.function_calls:
                        self.function_calls[caller_func] = set()
                    self.function_calls[caller_func].add(called_func_name)
                    if called_func_name in self.defined_functions:
                        self.call_graph.add_edge(caller_func, called_func_name)
        for child in node.children:
            self._collect_calls_in_body(caller_func, child)

    # Get the name of the called function
    def get_called_function_name(self, function_node):
        if function_node.type == 'identifier':
            return function_node.text.decode('utf8')
        else:
            return None

    # Match target functions
    def match_target_functions(self, target_functions):
        self.matched_functions = []
        for func in self.defined_functions:
            func_name = func.split('.')[-1]
            for target_func in target_functions:
                if func_name == target_func:
                    self.matched_functions.append(func)
                    break

    # Find external functions called by all target functions
    def find_common_called_functions(self):
        target_called_functions = []
        for func in self.matched_functions:
            called_funcs = self.function_calls.get(func, set())
            external_called_funcs = {func_name for func_name in called_funcs if func_name not in self.defined_functions}
            target_called_functions.append(external_called_funcs)

        if target_called_functions:
            common_called_funcs = set.intersection(*target_called_functions)
            self.common_called_functions = common_called_funcs
            for func in self.common_called_functions:
                self.call_graph.add_node(func)
                for caller_func in self.matched_functions:
                    if func in self.function_calls.get(caller_func, set()):
                        self.call_graph.add_edge(caller_func, func)
        else:
            self.common_called_functions = set()

    # Compute shortest path distances between target functions (undirected graph)
    def compute_distances(self):
        self.distances = {}
        undirected_graph = self.call_graph.to_undirected()
        for i, func1 in enumerate(self.matched_functions):
            for func2 in self.matched_functions[i+1:]:
                try:
                    distance = nx.shortest_path_length(undirected_graph, source=func1, target=func2)
                    self.distances[(func1, func2)] = distance
                except nx.NetworkXNoPath:
                    self.distances[(func1, func2)] = None

    # Draw the call graph
    def draw_call_graph(self, output_path):
        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(self.call_graph, k=0.5, iterations=50)
        node_colors = []
        for node in self.call_graph.nodes():
            if node in self.matched_functions:
                node_colors.append('red')
            elif node in self.common_called_functions:
                node_colors.append('green')
            else:
                node_colors.append('lightblue')
        nx.draw_networkx_nodes(self.call_graph, pos, node_color=node_colors, node_size=500)
        nx.draw_networkx_edges(self.call_graph, pos, arrows=True)
        nx.draw_networkx_labels(self.call_graph, pos, font_size=8)
        plt.axis('off')
        plt.title("Function Call Graph")
        plt.savefig(output_path)
        plt.close()

    # Save distance information to a file
    def save_distances(self, output_file):
        with open(output_file, 'w', encoding='utf-8') as f:
            for funcs, distance in self.distances.items():
                func1, func2 = funcs
                f.write(f"Distance between {func1} and {func2}: {distance}\n")
