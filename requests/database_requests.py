import json
from datetime import datetime
from typing import List, Dict

class RequestDatabase:
    def __init__(self, filename: str = 'requests/requests.json'):
        self.filename = filename
        self.data = self.load_data()

    def load_data(self) -> Dict:
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # Создаем новую базу если файла нет
            base_structure = {
                "requests": [],
                "next_request_id": 1
            }
            self.save_data(base_structure)
            return base_structure

    def save_data(self, data=None):
        if data is None:
            data = self.data
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_request(self, user_id: str, request_text: str):
        request_id = self.data["next_request_id"]
        new_request = {
            "request_id": request_id,
            "user_id": user_id,
            "request": request_text,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        }
        self.data["requests"].append(new_request)
        self.data["next_request_id"] = request_id + 1
        self.save_data()
        return request_id