from setuptools import setup, find_packages

setup(
    name="erpnext_custom",
    version="0.0.1",
    description="Oakglobal ERP custom app",
    author="Oakglobal",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[],
)
