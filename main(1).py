"""Простой калькулятор на FastAPI."""
import ast
import math
import operator
from typing import Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Calculator API",
    description="API простого калькулятора с поддержкой пошагового формирования и парсинга сложных выражений.",
    version="1.0.0",
)

MAX_EXPRESSION_LENGTH = 1000
ALLOWED_OPS = ("+", "-", "*", "/")

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def check_finite(value: float) -> float:
    """Бросает ошибку, если результат бесконечность или не число."""
    if not math.isfinite(value):
        raise ValueError("Результат выходит за допустимый диапазон чисел.")
    return value


def safe_eval(expression: str) -> float:
    """Безопасно вычисляет выражение с учётом приоритета операций и скобок."""
    expression = expression.strip()
    if not expression:
        raise ValueError("Выражение пустое.")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(f"Выражение длиннее {MAX_EXPRESSION_LENGTH} символов.")

    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, MemoryError, RecursionError):
        raise ValueError("Синтаксическая ошибка в математическом выражении.")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in OPERATORS:
                raise ValueError(f"Неподдерживаемая бинарная операция: {op_type.__name__}")
            left = _eval(node.left)
            right = _eval(node.right)
            if op_type is ast.Div and right == 0:
                raise ZeroDivisionError("Деление на ноль запрещено.")
            return OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in OPERATORS:
                raise ValueError(f"Неподдерживаемая унарная операция: {op_type.__name__}")
            return OPERATORS[op_type](_eval(node.operand))
        else:
            raise ValueError("Выражение содержит недопустимые элементы или переменные.")

    try:
        return check_finite(float(_eval(tree)))
    except RecursionError:
        raise ValueError("Выражение слишком глубоко вложено.")
    except OverflowError:
        raise ValueError("Результат выходит за допустимый диапазон чисел.")


def evaluate_or_400(expression: str) -> float:
    """Вычисляет выражение, ошибки вычисления превращает в ответ 400."""
    try:
        return safe_eval(expression)
    except (ValueError, ZeroDivisionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def basic_result(operation: str, value: float) -> dict:
    try:
        return {"operation": operation, "result": check_finite(value)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def wrap(expr: str) -> str:
    """Заключает выражение во внешние скобки, если их ещё нет."""
    expr = expr.strip()
    if expr.startswith("(") and expr.endswith(")"):
        depth = 0
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(expr) - 1:
                    break
        else:
            return expr
    return f"({expr})"


def operand_to_str(value: Union[float, str]) -> str:
    """Приводит операнд к строке, подвыражения берёт в скобки, чтобы сохранить приоритет."""
    if isinstance(value, str):
        return wrap(value)
    text = str(int(value)) if float(value).is_integer() and abs(value) < 1e15 else repr(float(value))
    return f"({text})" if value < 0 else text


def check_op(op: str) -> None:
    if op not in ALLOWED_OPS:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый оператор '{op}'. Разрешены: {', '.join(ALLOWED_OPS)}",
        )


class BasicOperationRequest(BaseModel):
    a: float = Field(..., allow_inf_nan=False, description="Первый операнд")
    b: float = Field(..., allow_inf_nan=False, description="Второй операнд")


class StepExpressionRequest(BaseModel):
    a: Union[float, str] = Field(..., description="Первый операнд или подвыражение")
    op: str = Field(..., description="Операция: '+', '-', '*', '/'")
    b: Union[float, str] = Field(..., description="Второй операнд или подвыражение")
    wrap_in_parentheses: bool = Field(
        default=True,
        description="Обернуть ли созданное выражение в скобки для сохранения приоритета",
    )


class AppendExpressionRequest(BaseModel):
    op: str = Field(..., description="Операция: '+', '-', '*', '/'")
    operand: Union[float, str] = Field(..., description="Число или подвыражение, например '(20 - 4) / (6 - 2)'")


class FullExpressionRequest(BaseModel):
    expression: str = Field(
        ...,
        max_length=MAX_EXPRESSION_LENGTH,
        examples=["(10 + 5) * 2 + (20 - 4) / (6 - 2)"],
        description="Полное математическое выражение",
    )


class CalculatorState:
    def __init__(self):
        self.current_expression: str = ""

    def clear(self):
        self.current_expression = ""


calc_state = CalculatorState()


def set_current_expression(expression: str) -> None:
    """Сохраняет выражение, только если оно корректно, иначе состояние не меняется."""
    evaluate_or_400(expression)
    calc_state.current_expression = expression


@app.post("/add", tags=["Базовые операции"])
def add(data: BasicOperationRequest):
    return basic_result("addition", data.a + data.b)


@app.post("/subtract", tags=["Базовые операции"])
def subtract(data: BasicOperationRequest):
    return basic_result("subtraction", data.a - data.b)


@app.post("/multiply", tags=["Базовые операции"])
def multiply(data: BasicOperationRequest):
    return basic_result("multiplication", data.a * data.b)


@app.post("/divide", tags=["Базовые операции"])
def divide(data: BasicOperationRequest):
    if data.b == 0:
        raise HTTPException(status_code=400, detail="Деление на ноль невозможно.")
    return basic_result("division", data.a / data.b)


@app.post("/expression/step", tags=["Управление выражением"])
def build_step_expression(data: StepExpressionRequest):
    """Создаёт выражение из a, op и b и делает его текущим."""
    check_op(data.op)

    part = f"{operand_to_str(data.a)} {data.op} {operand_to_str(data.b)}"
    if data.wrap_in_parentheses:
        part = wrap(part)

    set_current_expression(part)
    return {
        "message": "Выражение сформировано",
        "current_expression": calc_state.current_expression,
    }


@app.post("/expression/append", tags=["Управление выражением"])
def append_to_expression(data: AppendExpressionRequest):
    """Присоединяет к текущему выражению операцию и операнд."""
    check_op(data.op)

    if not calc_state.current_expression:
        raise HTTPException(
            status_code=400,
            detail="Текущее выражение пусто. Сначала создайте базовое выражение.",
        )

    new_expression = (
        f"{wrap(calc_state.current_expression)} {data.op} {operand_to_str(data.operand)}"
    )
    set_current_expression(new_expression)
    return {
        "message": "Выражение дополнено",
        "current_expression": calc_state.current_expression,
    }


@app.get("/expression", tags=["Управление выражением"])
def get_current_expression():
    """Возвращает текущее выражение."""
    return {
        "current_expression": calc_state.current_expression,
        "is_empty": calc_state.current_expression == "",
    }


@app.post("/expression/execute", tags=["Управление выражением"])
def execute_current_expression():
    """Вычисляет текущее выражение и возвращает результат."""
    if not calc_state.current_expression:
        raise HTTPException(status_code=400, detail="Текущее выражение пусто. Нечего выполнять.")
    return {
        "expression": calc_state.current_expression,
        "result": evaluate_or_400(calc_state.current_expression),
    }


@app.delete("/expression", tags=["Управление выражением"])
def clear_current_expression():
    """Очищает текущее выражение."""
    calc_state.clear()
    return {"message": "Выражение очищено", "current_expression": ""}


@app.post("/expression/set", tags=["Сложные выражения"])
def set_full_expression(data: FullExpressionRequest):
    """Принимает выражение строкой и делает его текущим."""
    set_current_expression(data.expression.strip())
    return {
        "message": "Выражение установлено",
        "current_expression": calc_state.current_expression,
    }


@app.post("/calculate", tags=["Сложные выражения"])
def calculate(data: FullExpressionRequest):
    """Вычисляет выражение из строки и сразу возвращает результат."""
    return {
        "expression": data.expression.strip(),
        "result": evaluate_or_400(data.expression),
    }
