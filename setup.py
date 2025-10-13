from setuptools import setup, find_packages

setup(
    name="jawm",
    version="1.0",
    packages=find_packages(),
    install_requires=[
        "PyYAML>=5.4.1",
    ],
    entry_points={
        'console_scripts': [
            'jawm = jawm.cli:main',
            'jawm-dev = jawm.cli_dev:main',
        ],
    },   
)
