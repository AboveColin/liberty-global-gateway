"""
Setup file for the compalf3896lg package
"""

from setuptools import setup

setup(
    name="compalf3896lg",
    version="1.0.0",
    description="An unofficial async Python client for the Compal F3896LG (Ziggo) cable gateway",
    author="AboveColin",
    author_email="colin@cdevries.dev",
    packages=["compalf3896lg"],
    install_requires=[
        "aiohttp",
    ],
    python_requires=">=3.11",
    url="https://github.com/abovecolin/compalf3896lg",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    long_description_content_type="text/markdown",
    long_description=open("README.md", encoding="utf-8").read(),
)
