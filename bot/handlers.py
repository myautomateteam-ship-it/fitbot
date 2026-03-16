{
  "meta": {
    "name": "FitBot — Схема логики",
    "description": "Визуальная схема работы бота. Не рабочий файл — только для понимания архитектуры.",
    "version": "2.0",
    "author": "Claude",
    "date": "2026-03-16"
  },

  "database_tables": {
    "users": {
      "description": "Основная таблица пользователей",
      "fields": {
        "id": "Уникальный ID юзера в системе",
        "telegram_id": "ID юзера в Telegram (уникальный)",
        "username": "Никнейм в Telegram",
        "first_name": "Имя",
        "role": "Роль: user / admin / superadmin",
        "status": "Статус: active / banned",
        "onboarding_done": "Заполнил ли профиль хотя бы частично",
        "sleep_time_last": "Когда последний раз написал что идёт спать (для расчёта сна)",
        "last_active": "Последняя активность"
      }
    },
    "profile": {
      "description": "Физические данные и цели юзера — основа для AI рекомендаций",
      "fields": {
        "user_id": "Ссылка на users.id",
        "age": "Возраст",
        "gender": "Пол: male / female",
        "height": "Рост в см",
        "weight": "Вес в кг",
        "target_weight": "Целевой вес",
        "goal": "Цель: lose / gain / maintain / health",
        "experience": "Опыт: beginner / intermediate / advanced",
        "activity_level": "Активность 1-4",
        "equipment": "Оборудование: home / gym / both",
        "days_per_week": "Дней тренировок в неделю",
        "session_duration": "Длина тренировки в минутах",
        "travel_time_gym": "Время до зала в минутах",
        "injuries": "Массив травм и ограничений",
        "diet_type": "Тип питания: standard / vegetarian / vegan / keto",
        "food_allergies": "Массив аллергий",
        "communication_style": "Стиль общения: friendly / strict / humor",
        "timezone_offset": "Часовой пояс юзера (число часов от UTC)",
        "bmr": "Базовый метаболизм (рассчитывается автоматически)",
        "tdee": "Суточный расход калорий с учётом активности",
        "daily_calories": "Целевые калории в день",
        "daily_protein": "Норма белка в граммах",
        "daily_fat": "Норма жиров в граммах",
        "daily_carbs": "Норма углеводов в граммах"
      }
    },
    "messages": {
      "description": "История диалога — память AI. Последние 20 сообщений передаются в GPT при каждом запросе",
      "fields": {
        "user_id": "Ссылка на users.id",
        "role": "Кто написал: user / assistant",
        "content": "Текст сообщения",
        "created_at": "Время сообщения"
      }
    },
    "user_notes": {
      "description": "Свободная память — факты о юзере которые AI извлёк из разговора",
      "fields": {
        "user_id": "Ссылка на users.id",
        "category": "Категория: preference / habit / context / health",
        "key": "Ключ заметки (уникальный для юзера)",
        "value": "Значение — что запомнили",
        "source": "Оригинальная фраза юзера",
        "is_active": "Актуальна ли заметка",
        "last_mentioned": "Когда последний раз упоминал"
      },
      "example": {
        "key": "hates_running",
        "value": "Не любит бег, предпочитает силовые",
        "source": "только не бег пожалуйста"
      }
    },
    "nutrition_log": {
      "description": "Лог питания — что съел за день",
      "fields": {
        "user_id": "Ссылка на users.id",
        "food_description": "Что написал юзер",
        "calories": "Калории",
        "protein": "Белки в граммах",
        "fat": "Жиры в граммах",
        "carbs": "Углеводы в граммах",
        "is_approximate": "Приблизительный расчёт (true/false)",
        "logged_at": "Время приёма пищи"
      }
    },
    "workout_plans": {
      "description": "Планы тренировок сгенерированные AI",
      "fields": {
        "user_id": "Ссылка на users.id",
        "plan_text": "Полный текст плана",
        "week_start": "Дата начала недели",
        "is_active": "Активный план (только один активный)"
      }
    },
    "daily_checkins": {
      "description": "Ежедневный чекин — состояние юзера на сегодня",
      "fields": {
        "user_id": "Ссылка на users.id",
        "date": "Дата",
        "weight": "Вес сегодня утром",
        "sleep_hours": "Часов сна (рассчитывается автоматически)",
        "energy_level": "Уровень энергии 1-5 (юзер выбирает кнопкой)",
        "workout_done": "Тренировка выполнена",
        "water_ml": "Выпито воды"
      }
    },
    "reminders": {
      "description": "Напоминания — scheduler проверяет каждую минуту",
      "fields": {
        "user_id": "Ссылка на users.id",
        "telegram_id": "ID в Telegram для отправки",
        "type": "Тип: morning / evening / workout / water / custom",
        "message": "Текст напоминания",
        "time_of_day": "Время в UTC формате HH:MM",
        "days_of_week": "Массив дней: [mon, tue, wed, thu, fri, sat, sun]",
        "use_gpt": "Генерировать текст через GPT (true) или отправить как есть (false)",
        "is_active": "Активно ли напоминание",
        "last_sent": "Когда последний раз отправили (защита от дублей)"
      }
    },
    "schedule": {
      "description": "Расписание юзера по дням недели",
      "fields": {
        "user_id": "Ссылка на users.id",
        "day_of_week": "День: mon/tue/wed/thu/fri/sat/sun",
        "wake_time": "Время подъёма",
        "sleep_time": "Время сна",
        "work_start": "Начало работы",
        "work_end": "Конец работы",
        "workout_time": "Время тренировки",
        "dnd_start": "Начало режима не беспокоить",
        "dnd_end": "Конец режима не беспокоить",
        "is_rest_day": "День отдыха"
      }
    }
  },

  "ai_modules": {
    "ai_main": {
      "description": "Главный AI модуль — живой разговор с юзером",
      "model": "gpt-4o-mini",
      "input": [
        "Системный промпт с данными профиля",
        "Текущее местное время юзера",
        "Калории и БЖУ за сегодня",
        "История последних 20 сообщений",
        "Заметки из user_notes",
        "Новое сообщение юзера"
      ],
      "output": "Живой текстовый ответ от Макса",
      "cost": "~$0.00047 за вызов"
    },
    "ai_extract": {
      "description": "Экстракция данных — работает параллельно с ai_main",
      "model": "gpt-4o-mini",
      "input": [
        "Сообщение юзера",
        "Текущее UTC и местное время",
        "Часовой пояс юзера"
      ],
      "output": {
        "profile": "Данные профиля если юзер их упомянул",
        "reminders": "Массив напоминаний если юзер просил напомнить"
      },
      "cost": "~$0.0001 за вызов"
    },
    "ai_kbju": {
      "description": "Расчёт КБЖУ по описанию еды",
      "model": "gpt-4o-mini",
      "input": "Текстовое описание еды",
      "output": {
        "calories": "Калории",
        "protein": "Белки",
        "fat": "Жиры",
        "carbs": "Углеводы",
        "is_approximate": "Насколько точен расчёт"
      },
      "cost": "~$0.00005 за вызов"
    },
    "ai_plan": {
      "description": "Генерация плана тренировок на неделю",
      "model": "gpt-4o-mini",
      "input": "Профиль юзера (цель, опыт, оборудование, травмы, дни, время)",
      "output": "Полный текст плана тренировок",
      "cost": "~$0.0008 за вызов (редко используется)"
    },
    "ai_reminder_text": {
      "description": "Генерация живого текста напоминания",
      "model": "gpt-4o-mini",
      "input": "Тип напоминания + контекст юзера",
      "output": "Живой персонализированный текст от Макса",
      "cost": "~$0.00007 за вызов"
    }
  },

  "flow": {
    "description": "Полная логика обработки сообщения от юзера",
    "nodes": [
      {
        "id": "1",
        "name": "Telegram Trigger",
        "description": "Юзер написал сообщение в бот",
        "type": "trigger"
      },
      {
        "id": "2",
        "name": "Проверка юзера",
        "description": "Ищем юзера в таблице users по telegram_id",
        "type": "database_read",
        "table": "users",
        "next_if_not_found": "3",
        "next_if_found": "4"
      },
      {
        "id": "3",
        "name": "Регистрация нового юзера",
        "description": "Создаём запись в users + пустой профиль в profile",
        "type": "database_write",
        "tables": ["users", "profile"],
        "next": "5"
      },
      {
        "id": "4",
        "name": "Проверка бана",
        "description": "Если status = banned — отправляем сообщение о блокировке и стоп",
        "type": "condition",
        "next_if_banned": "END",
        "next_if_active": "6"
      },
      {
        "id": "5",
        "name": "Первое приветствие",
        "description": "AI_MAIN генерирует живое первое сообщение зная имя юзера",
        "type": "ai_call",
        "module": "ai_main",
        "next": "END"
      },
      {
        "id": "6",
        "name": "Обновить last_active",
        "description": "Записываем время последней активности",
        "type": "database_write",
        "table": "users",
        "next": "7"
      },
      {
        "id": "7",
        "name": "Загрузка данных юзера",
        "description": "Параллельно загружаем: профиль, питание за сегодня, чекин, заметки",
        "type": "database_read",
        "tables": ["profile", "nutrition_log", "daily_checkins", "user_notes"],
        "next": "8"
      },
      {
        "id": "8",
        "name": "Роутер — тип сообщения",
        "description": "Определяем что написал юзер",
        "type": "router",
        "routes": {
          "sleep_words": "9 → Трекинг сна",
          "menu_button": "10 → Обработка кнопки меню",
          "food_words": "11 → Трекинг питания",
          "any_text": "12 → AI обработка"
        }
      },
      {
        "id": "9",
        "name": "Трекинг сна",
        "description": "Юзер написал что идёт спать. Сохраняем время в users.sleep_time_last. Утром когда напишет — вычтем разницу = время сна",
        "type": "database_write",
        "table": "users",
        "field": "sleep_time_last",
        "next": "AI_MAIN → ответ"
      },
      {
        "id": "10",
        "name": "Кнопки меню",
        "description": "Обработка нажатий кнопок главного меню",
        "type": "router",
        "routes": {
          "💪 Тренировка": "10a",
          "🥗 Питание": "10b",
          "📊 Прогресс": "10c",
          "📅 Расписание": "10d",
          "⚙️ Профиль": "10e"
        }
      },
      {
        "id": "10a",
        "name": "Тренировка",
        "description": "Проверяем есть ли активный план в workout_plans. Если да — показываем. Если нет — генерируем через AI_PLAN и сохраняем",
        "type": "database_read + ai_call",
        "table": "workout_plans"
      },
      {
        "id": "10b",
        "name": "Питание",
        "description": "Показываем инструкцию как логировать еду",
        "type": "message"
      },
      {
        "id": "10c",
        "name": "Прогресс",
        "description": "Читаем данные из daily_checkins и nutrition_log, формируем отчёт без AI",
        "type": "database_read",
        "tables": ["daily_checkins", "nutrition_log", "profile"]
      },
      {
        "id": "10d",
        "name": "Расписание",
        "description": "Читаем schedule юзера. Если пусто — просим рассказать",
        "type": "database_read",
        "table": "schedule"
      },
      {
        "id": "10e",
        "name": "Профиль",
        "description": "Показываем все данные из profile без AI",
        "type": "database_read",
        "table": "profile"
      },
      {
        "id": "11",
        "name": "Трекинг питания",
        "description": "Юзер написал что съел. Вызываем AI_KBJU для расчёта. Сохраняем в nutrition_log. Считаем остаток до нормы.",
        "type": "ai_call + database_write",
        "module": "ai_kbju",
        "table": "nutrition_log"
      },
      {
        "id": "12",
        "name": "Параллельная AI обработка",
        "description": "Запускаем одновременно два AI запроса",
        "type": "parallel",
        "parallel_tasks": {
          "task_1": {
            "name": "AI_MAIN — ответ юзеру",
            "description": "Генерирует живой ответ с учётом всего контекста",
            "module": "ai_main"
          },
          "task_2": {
            "name": "AI_EXTRACT — извлечение данных",
            "description": "Параллельно анализирует сообщение на наличие данных профиля и напоминаний",
            "module": "ai_extract"
          }
        },
        "next": "13"
      },
      {
        "id": "13",
        "name": "Сохранение данных профиля",
        "description": "Если AI_EXTRACT нашёл данные профиля (возраст, вес и тд) — сохраняем в profile. Если теперь есть все основные данные — пересчитываем BMR/TDEE/калории",
        "type": "condition + database_write",
        "table": "profile",
        "auto_calculate": ["bmr", "tdee", "daily_calories", "daily_protein", "daily_fat", "daily_carbs"],
        "next": "14"
      },
      {
        "id": "14",
        "name": "Сохранение напоминаний",
        "description": "Если AI_EXTRACT нашёл напоминания — сохраняем каждое в reminders с правильным UTC временем. Поддерживает несколько напоминаний за раз.",
        "type": "database_write",
        "table": "reminders",
        "next": "15"
      },
      {
        "id": "15",
        "name": "Отправка ответа",
        "description": "Отправляем ответ от AI_MAIN юзеру. Если онбординг завершён — показываем меню.",
        "type": "telegram_send",
        "next": "END"
      }
    ]
  },

  "scheduler": {
    "description": "Фоновый процесс — работает каждые 60 секунд независимо от сообщений юзеров",
    "interval": "60 секунд",
    "flow": [
      {
        "step": "1",
        "name": "Получить текущее время",
        "description": "datetime.utcnow() → HH:MM и день недели"
      },
      {
        "step": "2",
        "name": "Найти напоминания",
        "description": "SELECT из reminders WHERE time_of_day = текущее_время AND день IN days_of_week AND is_active = true"
      },
      {
        "step": "3",
        "name": "Проверка дублей",
        "description": "Сравниваем last_sent с текущей минутой — не отправляем дважды"
      },
      {
        "step": "4",
        "name": "Генерация текста",
        "description": "Если use_gpt = true → AI_REMINDER_TEXT генерирует живой текст. Если false → берём message из базы",
        "module": "ai_reminder_text"
      },
      {
        "step": "5",
        "name": "Отправка",
        "description": "bot.send_message → юзеру. Утренние напоминания добавляют кнопки выбора энергии"
      },
      {
        "step": "6",
        "name": "Обновить last_sent",
        "description": "Записываем время отправки в reminders.last_sent"
      }
    ]
  },

  "cost_per_user_monthly": {
    "description": "Расчёт стоимости на одного активного юзера в месяц",
    "assumptions": "10 сообщений в день, 30 дней",
    "ai_calls": {
      "ai_main": "300 вызовов × $0.00047 = $0.14",
      "ai_extract": "300 вызовов × $0.0001 = $0.03",
      "ai_kbju": "50 вызовов × $0.00005 = $0.003",
      "ai_plan": "2 вызова × $0.0008 = $0.002",
      "ai_reminder": "60 вызовов × $0.00007 = $0.004"
    },
    "total_ai": "$0.18/юзер в месяц",
    "infrastructure": "$0.18 (Railway + Supabase на 200 юзеров)",
    "total_per_user": "~$0.36/юзер в месяц",
    "total_200_users": "~$72/месяц"
  }
}

