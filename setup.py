from setuptools import setup, find_packages

setup(
    name="jawm",
    version="0.1.0",
    author_email="bioinformatics@age.mpg.de",
    description="just another workflow manager",
    packages=find_packages(),
    include_package_data=True,  # to include files like test.sh
    python_requires=">=3.8",
    install_requires=[
        "PyYAML>=5.4.1",
        "argparse",
    ],
    entry_points={
        'console_scripts': [
            'jawm = jawm.cli:main',
            'jawm-dev = jawm.cli_dev:main',
        ],
    },
    scripts=["jawm/data/jawm-test"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
    url="https://github.com/mpg-age-bioinformatics/jawm",
)
