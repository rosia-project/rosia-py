from typing import Any, Callable, List, Type, TypeVar, TypedDict

from rosia.frontend.Port import InputPort
from rosia.utils import get_class_effective_init, record_init_args, NodeInitArgs
from typing import Optional
import inspect
import ast
import textwrap

T = TypeVar("T")


class RosiaAnnotations(TypedDict):
    original_init: Callable
    original_cls: Type
    init_args: Optional[NodeInitArgs]


def check_rosia_annotations(rosia_annotations: RosiaAnnotations) -> None:
    if rosia_annotations["original_init"] is None:
        raise ValueError(
            f"Original init is not set for class {rosia_annotations['original_cls'].__name__}"
        )
    if rosia_annotations["original_cls"] is None:
        raise ValueError(
            f"Original cls is not set for class {rosia_annotations['original_cls'].__name__}"
        )
    if rosia_annotations["init_args"] is None:
        raise ValueError(
            f"Init args are not set for class {rosia_annotations['original_cls'].__name__}"
        )


def get_rosia_annotations(cls: Any) -> RosiaAnnotations:
    try:
        return getattr(cls, "_rosia_annotations")
    except AttributeError:
        raise ValueError(f"Class {cls.__name__} is not annotated with @Node")


def update_rosia_annotations(cls: Any, new_annotations: RosiaAnnotations) -> None:
    if not hasattr(cls, "_rosia_annotations"):
        setattr(cls, "_rosia_annotations", new_annotations)
    else:
        old_annotations = get_rosia_annotations(cls)
        old_annotations.update(new_annotations)


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
    _rosia_annotations = RosiaAnnotations(
        original_init=original_init, original_cls=cls, init_args=None
    )
    update_rosia_annotations(cls, _rosia_annotations)
    setattr(cls, "__init__", record_init_args)
    return cls
