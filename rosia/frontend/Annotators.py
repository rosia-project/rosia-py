from typing import Callable, List, Type, TypeVar

from rosia.frontend.Port import InputPort
from rosia.utils import get_class_effective_init, record_init_args

import inspect
import ast
import textwrap

T = TypeVar("T")


def analyze_output_ports(func: Callable):
    src = inspect.getsource(func)
    src = textwrap.dedent(src)
    tree = ast.parse(src)
    func_node = None
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func.__name__
        ):
            func_node = node
            break
    if func_node is None:
        raise ValueError(f"Function {func.__name__} not found in source code")

    class OutputPortCollector(ast.NodeVisitor):
        def __init__(self):
            self.output_port_names: List[str] = []

        def visit_Call(self, node: ast.Call):
            func_expr = node.func
            if (
                isinstance(func_expr, ast.Attribute)
                and isinstance(func_expr.value, ast.Name)
                and func_expr.value.id == "self"
            ):
                self.output_port_names.append(func_expr.attr)
            self.generic_visit(node)

    collector = OutputPortCollector()
    collector.visit(func_node)
    return collector.output_port_names


def reaction(triggers: List[InputPort]) -> Callable[[Callable], Callable]:
    def decorator(func: Callable) -> Callable:
        output_port_names = analyze_output_ports(func)
        for input_port in triggers:
            input_port._add_trigger_function(func)
            input_port.affected_output_port_names = output_port_names
        return func

    return decorator


def Node(cls: Type[T]) -> Type[T]:
    original_init = get_class_effective_init(cls)
    setattr(cls, "_original_init", original_init)
    setattr(cls, "_original_cls", cls)
    setattr(cls, "__init__", record_init_args)
    return cls
