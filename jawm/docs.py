from ._docs_param import PROCESS_PARAM_DOCS

def jawm_help(class_name: str = "Process", param: str = None):
    """
    Show help for a class or a specific parameter or with examples.
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
            print("\nUse: jawm_help('Process', 'key/param_name') for more details.")
