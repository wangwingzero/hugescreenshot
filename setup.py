from setuptools import setup, find_packages

setup(
    name="screenshot_tool",
    version="2.5.1",
    packages=find_packages(),
    install_requires=[
        "PySide6",
        "rapidocr_onnxruntime",
        "opencv-python",
        "numpy",
        "mss",
        "pywin32",
    ],
)
