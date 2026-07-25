"""
Setup file for the liberty-global-gateway package
"""

from setuptools import setup

setup(
    name="liberty-global-gateway",
    version="2.0.0",
    description=(
        "An unofficial async Python client for Liberty Global cable gateways "
        "(Ziggo SmartWifi, UPC Connect Box, Virgin Media Hub, Sunrise, "
        "Unitymedia) - Sagemcom F3896LG / F3897LG / F5685LGB / F5685LGE and "
        "Compal CH7465LG"
    ),
    author="AboveColin",
    author_email="colin@cdevries.dev",
    packages=["liberty_global_gateway"],
    install_requires=[
        "aiohttp",
    ],
    python_requires=">=3.11",
    url="https://github.com/abovecolin/liberty-global-gateway",
    keywords=[
        "ziggo",
        "upc",
        "virgin-media",
        "unitymedia",
        "sunrise",
        "liberty-global",
        "sagemcom",
        "compal",
        "connect-box",
        "smartwifi",
        "docsis",
        "router",
        "f3896lg",
        "f3897lg",
        "f5685lgb",
        "f5685lge",
        "ch7465lg",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    long_description_content_type="text/markdown",
    long_description=open("README.md", encoding="utf-8").read(),
)
