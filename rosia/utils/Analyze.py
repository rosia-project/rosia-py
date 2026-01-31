from rosia.utils import empty_function


def get_class_effective_init(cls):
    for base in cls.__mro__:
        if "__init__" in base.__dict__:
            return base.__dict__["__init__"]
    return empty_function
