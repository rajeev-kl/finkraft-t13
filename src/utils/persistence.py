from typing import List, Dict, Any
import json
import os

def load_email_threads(file_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r') as file:
        return json.load(file)

def save_email_threads(file_path: str, threads: List[Dict[str, Any]]) -> None:
    with open(file_path, 'w') as file:
        json.dump(threads, file, indent=4)

def append_email_thread(file_path: str, thread: Dict[str, Any]) -> None:
    threads = load_email_threads(file_path)
    threads.append(thread)
    save_email_threads(file_path, threads)