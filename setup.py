from setuptools import setup, find_packages

setup(
    name="healix",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "playwright>=1.40.0",
        "beautifulsoup4>=4.12.0",
        "requests>=2.31.0",
    ],
    python_requires=">=3.8",
)
