"""Regression test for the per-instance init_args isolation.

Prior to the fix, ``record_init_args`` wrote ``init_args`` straight into the
class-level ``_rosia_annotations`` dict. Because the dict is shared across
every instance of the same ``@Node`` subclass (and shared with the clone
produced by ``clone_class_detached``), each construction would clobber the
previous instance's args, leaving every instance pointing at the last-set
value.

This test creates two Timer instances with different intervals and verifies
that they retain distinct ``init_args`` after both are constructed, both via
the captured ``NodeRuntime.node_init_args`` snapshot and via the diagram-graph
output.
"""

from rosia import Application
from rosia.diagram.diagram import build_graph
from rosia.time import Timer, ms


def test_two_timers_keep_distinct_init_args():
    app = Application()
    fast = app.create_node(Timer(interval=2 * ms))
    slow = app.create_node(Timer(interval=100 * ms))

    fast_info = app.node_infos[fast.node_name]
    slow_info = app.node_infos[slow.node_name]

    fast_runtime_args = fast_info.node.node_init_args
    slow_runtime_args = slow_info.node.node_init_args

    assert fast_runtime_args is not None
    assert slow_runtime_args is not None
    # kwargs were used at construction; values must match what was passed in.
    assert fast_runtime_args.kwargs["interval"] == 2 * ms
    assert slow_runtime_args.kwargs["interval"] == 100 * ms

    # Diagram graph builder must surface the same per-instance values.
    graph = build_graph(app.node_infos)
    by_name = {node.name: node for node in graph.nodes}
    fast_diagram = by_name[fast.node_name]
    slow_diagram = by_name[slow.node_name]
    assert fast_diagram.init_args is not None
    assert slow_diagram.init_args is not None
    assert fast_diagram.init_args.kwargs["interval"] == 2 * ms
    assert slow_diagram.init_args.kwargs["interval"] == 100 * ms


if __name__ == "__main__":
    test_two_timers_keep_distinct_init_args()
    print("ok")
