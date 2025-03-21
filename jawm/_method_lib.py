def add_methods_from(*modules):
    def decorator(cls):
        for module in modules:
            for method in getattr(module, "__methods__", []):
                setattr(cls, method.__name__, method)
        return cls
    return decorator

def register_method(method_list):
    def wrapper(func):
        method_list.append(func)
        return func
    return wrapper
