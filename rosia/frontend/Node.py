from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Type, TypeVar

from rosia.frontend.Port import InputPort

import inspect
import ast
import textwrap

T = TypeVar("T")


def reaction(triggers: List[InputPort]) -> Callable[[Callable], Callable]:
    def decorator(func: Callable) -> Callable:
        setattr(func, "_is_reaction", True)

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

        for input_port in triggers:
            input_port._add_trigger_function(func)
            input_port.affected_output_port_names = collector.output_port_names
        return func

    return decorator


@dataclass
class NodeInitArgs:
    args: Any
    kwargs: Dict[str, Any]


def Node(cls: Type[T]) -> Type[T]:
    def stub_init(self, *args, **kwargs):
        pass

    def get_effective_init(cls):
        for base in cls.__mro__:
            if "__init__" in base.__dict__:
                return base.__dict__["__init__"]
        return stub_init

    original_init = get_effective_init(cls)
    setattr(cls, "_original_init", original_init)
    # We have to record the init function because it will be overridden by the record_init_args init function
    setattr(cls, "_original_cls", cls)

    def record_init_args(self, *args, **kwargs):
        setattr(self, "_NodeInitArgs", NodeInitArgs(args, kwargs))

    setattr(cls, "__init__", record_init_args)
    return cls
