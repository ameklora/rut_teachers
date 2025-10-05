import json
from typing import Dict, List
from datetime import datetime
from statistics import mean


class Database:
    def __init__(self, filename: str = 'database/database.json'):
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
                    department: str, title: str, subjects: List[str]) -> str:
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
            "overall_rating": {"average": 0, "count": 0, "total": []},
            "reviews": []
        }
        self.data["teachers"].append(new_teacher)
        self.data["next_teacher_id"] = teacher_id + 1
        self.save_data()
        return teacher_id

    def get_teacher_by_id(self, teacher_id: int):
        for teacher in self.data["teachers"]:
            if teacher["id"] == teacher_id:
                return teacher
        return None

    def get_review_by_id(self, review_id: int):
        """
        Находит отзыв по review_id и возвращает копию с актуальными данными
        """
        for teacher in self.data["teachers"]:
            for review in teacher["reviews"]:
                if review["review_id"] == review_id:
                    # Возвращаем копию отзыва с teacher_id
                    review_copy = review.copy()
                    review_copy["teacher_id"] = teacher["id"]
                    return review_copy
        return None

    def smart_search(self, query: str):
        """
        Умный поиск с учетом релевантности, рейтинга и количества отзывов
        """
        results = []
        query = query.lower().strip()

        if not query or len(query) < 2:
            return []

        for teacher in self.data["teachers"]:
            score = 0
            full_name = f"{teacher['surname']} {teacher['name']} {teacher['middlename']}".lower()

            # Бонус за популярность (больше отзывов = выше в результатах)
            popularity_bonus = min(teacher['overall_rating']['count'] * 2, 20)  # макс +20 баллов

            # 1. ТОЧНЫЕ СОВПАДЕНИЯ (высший приоритет)
            if teacher['surname'].lower() == query:
                score = 100 + popularity_bonus

            # 2. Имя+Фамилия (например, "Иван Иванов")
            elif f"{teacher['name'].lower()} {teacher['surname'].lower()}" == query:
                score = 95 + popularity_bonus

            # 3. Фамилия + первая буква имени ("Иванов И")
            elif f"{teacher['surname'].lower()} {teacher['name'][0].lower()}" == query:
                score = 90 + popularity_bonus

            # 4. Начало фамилии
            elif teacher['surname'].lower().startswith(query):
                score = 80 + popularity_bonus

            # 5. Фамилия содержит запрос
            elif query in teacher['surname'].lower():
                score = 70 + popularity_bonus

            # 6. Полное ФИО содержит запрос
            elif query in full_name:
                score = 60 + popularity_bonus

            # 7. Только имя
            elif teacher['name'].lower() == query:
                score = 50 + popularity_bonus

            # 8. Только отчество
            elif teacher['middlename'].lower() == query:
                score = 40 + popularity_bonus

            # 9. Кафедра/предметы (низкий приоритет)
            elif (query in teacher['department'].lower() or
                  any(query in subject.lower() for subject in teacher['subjects'])):
                score = 30

            if score > 0:
                # Дополнительный бонус за высокий рейтинг
                rating_bonus = teacher['overall_rating']['average'] * 2  # +10 баллов за 5.0
                results.append({
                    'teacher': teacher,
                    'score': score + rating_bonus
                })

        # Сортируем по релевантности
        results.sort(key=lambda x: x['score'], reverse=True)
        return [result['teacher'] for result in results]

    def search_teachers(self, query: str):
        """Старый метод поиска для обратной совместимости"""
        return self.smart_search(query)

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
            "user_votes": {}
        }
        reviewed_teacher["reviews"].append(new_review)
        reviewed_teacher["overall_rating"]["count"] += 1
        reviewed_teacher["overall_rating"]["total"].append(rating)
        reviewed_teacher["overall_rating"]["average"] = mean(reviewed_teacher["overall_rating"]["total"])
        self.data["next_review_id"] = review_id + 1
        self.save_data()
        return review_id

    def rate_review(self, review_id: int, user_id: str, like: int = 0, dislike: int = 0):
        """
        Обновляет рейтинг отзыва и возвращает True/False в зависимости от успеха
        """
        for teacher in self.data["teachers"]:
            for review in teacher["reviews"]:
                if review["review_id"] == review_id:
                    # Инициализируем user_votes если нет
                    if "user_votes" not in review:
                        review["user_votes"] = {}

                    previous_vote = review["user_votes"].get(user_id)

                    # Убираем предыдущий голос
                    if previous_vote == "like":
                        review["review_likes"] = max(0, review["review_likes"] - 1)
                    elif previous_vote == "dislike":
                        review["review_dislikes"] = max(0, review["review_dislikes"] - 1)

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
                    return True  # Успешно проголосовали

        return False  # Отзыв не найден

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
        teacher = self.get_teacher_by_id(teacher_id)
        return teacher["reviews"] if teacher and teacher["reviews"] else []

    def get_teacher_reviews_page(self, teacher_id: int, page: int, page_size: int = 5):
        """
        Получение страницы отзывов преподавателя.
        Всегда возвращает список отзывов длиной <= page_size.
        """
        reviews = self.get_teacher_reviews(teacher_id)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        return reviews[start_idx:end_idx]

    def get_teacher_reviews_pages_count(self, teacher_id: int, page_size: int = 5):
        """
        Получение количества страниц отзывов преподавателя для пагинации.
        """
        total_reviews = self.get_teacher_reviews_count(teacher_id)
        return (total_reviews + page_size - 1) // page_size  # округление вверх

    def get_teacher_reviews_count(self, teacher_id: int) -> int:
        teacher = self.get_teacher_by_id(teacher_id)
        return len(teacher["reviews"]) if teacher and teacher["reviews"] else 0

    def get_teacher_review_by_index(self, teacher_id: int, index: int):
        reviews = self.get_teacher_reviews(teacher_id)
        return reviews[index] if 0 <= index < len(reviews) else None

    def get_all_teachers(self) -> List[Dict]:
        """Получение всех преподавателей"""
        return self.data["teachers"]

    def get_teachers_count(self) -> int:
        """Получение общего количества преподавателей"""
        return len(self.data["teachers"])

    def get_teachers_page(self, page: int, page_size: int = 6) -> List[Dict]:
        """Получение страницы преподавателей"""
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        return self.data["teachers"][start_idx:end_idx]