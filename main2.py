from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator, model_validator


class UserRegistration(BaseModel):
    username: str
    email: EmailStr
    password: str
    password_confirm: str = Field(exclude=True)
    age: int
    registration_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    real_name: str
    phone: str

    @field_validator('username')
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not 3 <= len(value) <= 20:
            raise ValueError('Логин должен содержать от 3 до 20 символов')

        if re.fullmatch(r'[A-Za-z0-9_]+', value) is None:
            raise ValueError(
                'Логин может содержать только латинские буквы, цифры и подчёркивание'
            )

        return value

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        errors = []

        if len(value) < 8:
            errors.append('Пароль должен содержать минимум 8 символов')
        if re.search(r'[0-9]', value) is None:
            errors.append('Пароль должен содержать хотя бы одну цифру')
        if re.search(r'[A-Z]', value) is None:
            errors.append('Пароль должен содержать хотя бы одну заглавную букву')
        if re.search(r'[a-z]', value) is None:
            errors.append('Пароль должен содержать хотя бы одну строчную букву')

        if errors:
            raise ValueError('; '.join(errors))

        return value

    @field_validator('age', mode='before')
    @classmethod
    def validate_age(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError('Возраст должен быть целым числом')

        if not 18 <= value <= 120:
            raise ValueError('Возраст должен быть от 18 до 120 лет включительно')

        return value

    @field_validator('real_name')
    @classmethod
    def validate_real_name(cls, value: str) -> str:
        if len(value) < 2:
            raise ValueError('Имя должно содержать минимум 2 символа')

        if not value[0].isupper():
            raise ValueError('Имя должно начинаться с заглавной буквы')

        return value

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if re.fullmatch(r'\+[0-9]-[0-9]{3}-[0-9]{2}-[0-9]{2}', value) is None:
            raise ValueError('Телефон должен иметь формат +X-XXX-XX-XX')

        return value

    @model_validator(mode='after')
    def validate_passwords_match(self) -> UserRegistration:
        if self.password != self.password_confirm:
            raise ValueError('Пароль и подтверждение пароля не совпадают')

        return self


def register_user(data: dict[str, Any]) -> UserRegistration | list[str]:
    try:
        return UserRegistration.model_validate(data)
    except ValidationError as error:
        readable_errors = []
        field_names = {
            'username': 'Логин',
            'email': 'Email',
            'password': 'Пароль',
            'password_confirm': 'Подтверждение пароля',
            'age': 'Возраст',
            'registration_date': 'Дата регистрации',
            'real_name': 'Имя',
            'phone': 'Телефон',
        }

        for item in error.errors():
            location = item['loc']
            field = location[0] if location else None
            message = item['msg'].removeprefix('Value error, ')

            if item['type'] == 'missing':
                message = 'Обязательное поле не заполнено'
            elif field == 'email':
                message = 'Укажите корректный email-адрес'

            if field in field_names:
                readable_errors.append(f'{field_names[field]}: {message}')
            else:
                readable_errors.append(message)

        return readable_errors


class RecursiveData(BaseModel):
    data: Any
    child: RecursiveData | None = None


def create_recursive_model(data: dict[str, Any]) -> RecursiveData:
    return RecursiveData.model_validate(data)


if __name__ == '__main__':
    user_data = {
        'username': 'student_123',
        'email': 'student@example.com',
        'password': 'Password123',
        'password_confirm': 'Password123',
        'age': 20,
        'real_name': 'Иван',
        'phone': '+1-234-56-78',
    }

    registration_result = register_user(user_data)

    if isinstance(registration_result, UserRegistration):
        print('Пользователь успешно зарегистрирован')
        print(registration_result.model_dump())
    else:
        print('Ошибки регистрации:')
        for error_message in registration_result:
            print(error_message)

    recursive_data = {
        'data': 'первый уровень',
        'child': {
            'data': 'второй уровень',
            'child': {
                'data': 'третий уровень',
            },
        },
    }

    recursive_model = create_recursive_model(recursive_data)
    print(recursive_model.model_dump_json(indent=2, exclude_none=True))
