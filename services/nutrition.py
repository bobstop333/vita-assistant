def calculate_plan(weight: int, height: int, age: int, gender: str, goal: str, activity_level: str = "moderate"):
    """
    Расчёт КБЖУ по формуле Харриса-Бенедикта + коэффициент активности.
    activity_level: sedentary | light | moderate | active | very_active
    """
    # BMR (базовый обмен)
    if gender == 'male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    # Коэффициент активности
    activity_factors = {
        "sedentary":   1.2,    # сидячий образ жизни
        "light":       1.375,  # лёгкая активность 1-3 раза в неделю
        "moderate":    1.55,   # умеренная активность 3-5 раз в неделю
        "active":      1.725,  # высокая активность 6-7 раз в неделю
        "very_active": 1.9,    # очень высокая (спортсмены, физический труд)
    }
    factor = activity_factors.get(activity_level, 1.55)
    tdee = bmr * factor

    goal_lower = goal.lower()
    if "pohud" in goal_lower or "похудение" in goal_lower:
        calories = tdee - 500
    elif "mass" in goal_lower or "набор" in goal_lower:
        calories = tdee + 300
    else:
        calories = tdee

    calories = int(calories)

    protein = weight * 2
    fat = int(weight * 1)

    protein_cal = protein * 4
    fat_cal = fat * 9

    carbs_cal = calories - (protein_cal + fat_cal)
    if carbs_cal < 0:
        carbs_cal = 0
    carbs = carbs_cal / 4

    return {
        "calories": calories,
        "protein": int(protein),
        "fat": int(fat),
        "carbs": int(carbs)
    }
