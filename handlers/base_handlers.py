from abc import ABC, abstractmethod
from tree_sitter import Parser, Language

class LanguageHandler(ABC):
    def __init__(self, parser):
        self.parser = parser

    @abstractmethod
    def extract_functions(self, source_code):
        pass

    def normalize_code(self, code):
        return code.replace(" ", "").replace("\t", "").replace("\n", "")

    def compare_functions(self, funcs_before, funcs_after):
        modified_functions = []

        for func_name in funcs_before:
            if func_name not in funcs_after:
                modified_functions.append(func_name)

        for func_name in funcs_after:
            if func_name in funcs_before:
                normalized_before = self.normalize_code(funcs_before[func_name])
                normalized_after = self.normalize_code(funcs_after[func_name])

                if normalized_before != normalized_after:
                    modified_functions.append(func_name)

        return modified_functions
