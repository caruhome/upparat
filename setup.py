import io
import re

from setuptools import find_packages
from setuptools import setup

with io.open("src/upparat/__init__.py", "rt", encoding="utf8") as f:
    version = re.search(r'__version__ = "(.*?)"', f.read()).group(1)

setup(
    name="upparat",
    version=version,
    description="Update Service for AWS IoT Core",
    url="https://github.com/caruhome/upparat",
    long_description_content_type="text/markdown",
    long_description="The Upparat is a secure and robust service that runs on your IoT device to download and install files such as firmware updates. [Learn more](https://github.com/caruhome/upparat).",  # noqa
    python_requires=">=3.6",
    packages=find_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=["paho-mqtt>=1.4.0", "backoff>=1.8.1", "pysm>=0.3.7"],
    extras_require={
        "dev": ["pytest", "pytest-mock", "boto3", "ipdb", "coverage"],
        "sentry": ["sentry-sdk"],
    },
    entry_points={"console_scripts": ["upparat=upparat.cli:main"]},
)
