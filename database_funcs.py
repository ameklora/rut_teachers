import json
from typing import Dict, List
from datetime import datetime
from statistics import mean

class Database:
    def __init__(self, filename: str = 'database.json'):
        self.filename = filename
        self.data = self.load_data()


    def load_data(self) -> Dict:
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f'error: файл {self.filename} не найден')
            return None

    def save_data(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_teacher(self, surname: str, name: str, middlename: str, institute: str,
                    department: str, title: str, subjects: List[str], overall_rating: dict = 0, reviews: List[dict] = []) -> str:

        teacher_id = self.data["next_teacher_id"]

        new_teacher = {
            "id": teacher_id,
            "surname": surname,
            "name": name,
            "middlename": middlename,
            "institute": institute,
            "department": department,
            "title": title,
            "subjects": subjects,
            "overall_rating": {
                "average": 0,
                "count": 0,
                "total": []
              },
            "reviews": []
        }

        self.data["teachers"].append(new_teacher)
        self.data["next_teacher_id"] = teacher_id + 1
        self.save_data()

        return teacher_id

    def get_teacher_by_id(self, teacher_id: int): #поиск препода по id
        for teacher in self.data["teachers"]:
            if teacher["id"] == teacher_id:
                return teacher
        return None

    def get_review_by_id(self, review_id: int):
        for teacher in self.data["teachers"]:
            for review in teacher["reviews"]:
                if review["review_id"] == review_id:
                    return review
        return None

    def search_teachers(self, query: str):
        results = []
        query = query.lower()

        for teacher in self.data["teachers"]:
            #поиск по фио
            if teacher["surname"].lower() in query: #сначала смотрим по фамилии, если нет - то по имени отчеству
                results.append(teacher)
                continue
            elif teacher["name"].lower() in query or teacher["name"].lower() in query:
                results.append(teacher)
                continue
        return results

    def add_review(self, teacher_id: int, user_id: str, rating: int, comment: str):
        reviewed_teacher = self.get_teacher_by_id(teacher_id)
        if not reviewed_teacher:
            return False
        review_id = self.data["next_review_id"]

        new_review = {
            "review_id": review_id,
            "user_id": user_id,
            "rating": rating,
            "comment": comment,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "review_likes": 0,
            "review_dislikes": 0,
        }

        #добавляем отзыв и обновляем рейтинг
        reviewed_teacher["reviews"].append(new_review)
        reviewed_teacher["overall_rating"]["count"] +=1
        reviewed_teacher["overall_rating"]["total"].append(new_review["rating"])
        reviewed_teacher["overall_rating"]["average"] = mean(reviewed_teacher["overall_rating"]["total"])
        self.data["next_review_id"] = review_id + 1
        self.save_data()

        return review_id

    def rate_review(self, review_id: int, user_id: str, like: int = 0, dislike: int = 0):
        review = self.get_review_by_id(review_id)
        if not review:
            return False

        # Создаем структуру для хранения голосов
        if "user_votes" not in review:
            review["user_votes"] = {}

        previous_vote = review["user_votes"].get(user_id)

        # Убираем предыдущий голос
        if previous_vote == "like":
            review["review_likes"] -= 1
        elif previous_vote == "dislike":
            review["review_dislikes"] -= 1

        # Добавляем новый голос
        if like == 1:
            review["review_likes"] += 1
            review["user_votes"][user_id] = "like"
        elif dislike == 1:
            review["review_dislikes"] += 1
            review["user_votes"][user_id] = "dislike"
        else:
            # Удаляем голос, если это отмена
            review["user_votes"].pop(user_id, None)

        self.save_data()
        return True

    def get_top_teachers(self, limit: int = 5):
        teachers_with_ratings = [
            teacher for teacher in self.data["teachers"]
            if teacher["overall_rating"]["count"] > 0
        ]

        sorted_teachers = sorted(
            teachers_with_ratings,
            key=lambda x: x["overall_rating"]["average"],
            reverse=True
        )

        return sorted_teachers[:limit]

    def get_teacher_reviews(self, teacher_id: int):
        #получение отзывов препода
        return self.get_teacher_by_id(teacher_id)["reviews"] if self.get_teacher_by_id(teacher_id)["reviews"] else []


    def get_most_liked_review(self, teacher_id: int):
        #самый залайканный отзыв на препода, еще не сделал
        reviews = self.get_teacher_reviews(teacher_id)
        return reviews


