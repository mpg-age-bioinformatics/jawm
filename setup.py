# Bridge to pyproject.toml for old tools
from setuptools import setup
setup(
    name="jawm",
    version="0.1.0",
    extras_require={
        "full": [
            "pandas>=1.1",
            "openpyxl>=3.0",
            "requests"
        ]
    },
)