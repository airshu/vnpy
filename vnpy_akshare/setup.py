from setuptools import setup, find_packages

setup(
    name="vnpy_akshare",
    description="AKShare datafeed plugin for VeighNa",
    author="vnpy community",
    packages=find_packages(),
    install_requires=[
        "akshare>=1.11.0",
        "pandas>=2.0.0",
    ],
    python_requires=">=3.10",
)
