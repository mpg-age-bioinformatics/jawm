def add_methods_from(*modules):
    """
    Class decorator to dynamically add methods from given modules.
    Each module must define a __methods__ list containing functions to attach.
    """
    def decorator(cls):
        for module in modules:
            for method in getattr(module, "__methods__", []):
                setattr(cls, method.__name__, method)
        return cls
    return decorator


def register_method(method_list):
    """
    Function decorator that registers the given method into a provided method list.
    Used to collect methods that will later be added to a class dynamically.
    """
    def wrapper(func):
        method_list.append(func)
        return func
    return wrapper
