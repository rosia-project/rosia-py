from rosia.utils import empty_function


def get_class_effective_init(cls):
    for base in cls.__mro__:
        if "__init__" in base.__dict__:
            return base.__dict__["__init__"]
    return empty_function


def clone_class_detached(original_cls, new_name):
    new_namespace = dict(original_cls.__dict__)
    for key in ["__dict__", "__weakref__", "__module__"]:
        new_namespace.pop(key, None)
    return type(new_name, original_cls.__bases__, new_namespace)
