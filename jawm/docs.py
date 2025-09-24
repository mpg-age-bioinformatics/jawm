from ._docs_param import PROCESS_PARAM_DOCS

def jhelp(class_name: str = "Process", param: str = None):
    """
    Display documentation for jawm classes, parameters, examples, or usage guides.

    By default, this function shows all available parameters, how-to guides, and
    usage examples for the Process class.

    Parameters:
    -----------
    class_name : str
        The class to retrieve help for. Default is "Process".

    param : str
        A specific parameter name, example key, or how-to topic to retrieve detailed
        documentation for. If not provided, a summary of all available topics will be shown.

    Usage Examples:
    ---------------
    >>> from jawm import jhelp

    # Show all Process documentation categories (parameters, how-tos, examples)
    >>> jhelp()

    # Show help for a specific parameter
    >>> jhelp("Process", "script")

    # Show a usage example
    >>> jhelp("Process", "example_hello_world")

    # Show a how-to guide
    >>> jhelp("Process", "howto_set_monitoring")

    """

    if class_name not in ["Process"]:
        print(f"Help for class '{class_name}' is not available.")
        return

    if class_name == "Process":
        if param:
            doc = PROCESS_PARAM_DOCS.get(param)
            if not doc:
                print(f"No documentation found for key '{param}'!")
                return

            if doc.get("category") == "parameter":
                print(f"\nProcess Parameter: `{param}`")
            elif doc.get("category") == "example":
                print(f"\nProcess Example: {param}")
            else:
                print(f"\nProcess HowTo: {param}")

            if doc.get("required"):
                print(f"  Mandatory: YES")
            
            if "description" in doc:
                print(f"  Description: {doc['description']}")

            if "note" in doc:
                print(f"  Note: {doc['note']}")

            if "type" in doc:
                print(f"  Type: {doc['type']}")

            if "default" in doc:
                print(f"  Default: {doc['default']}")

            if "allowed" in doc:
                print(f"  Allowed values: {doc['allowed']}")

            if "example" in doc:
                print("  Example:")
                print("  ```")
                for line in doc["example"].splitlines():
                    print(f"  {line}")
                print("  ```")

            if "yaml_example" in doc:
                print("  Example (YAML):")
                print("  ```")
                for line in doc["yaml_example"].splitlines():
                    print(f"  {line}")
                print("  ```")
        else:
            print("Available docs for Process parameters:::")
            for key in (k for k, v in PROCESS_PARAM_DOCS.items() if v.get("category") == "parameter"):
                print(f"  - {key}")
            print("\nAvailable docs for Process howto:::")
            for key in (k for k, v in PROCESS_PARAM_DOCS.items() if v.get("category") == "howto"):
                print(f"  - {key}")
            print("\nAvailable docs for example uses:::")
            for key in (k for k, v in PROCESS_PARAM_DOCS.items() if v.get("category") == "example"):
                print(f"  - {key}")
            print("\nUse: jhelp('Process', 'key/param_name') for more details.")
