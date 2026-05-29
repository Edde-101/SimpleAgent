import os
from pathlib import Path


def file_search(keyword: str) -> list:
    results = []
    for root, dirs, files in os.walk(Path.home()):
        for file in files:
            if keyword in file:
                results.append(os.path.join(root, file))
    return results
