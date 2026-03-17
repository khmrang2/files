"""짧은 태스크 ID 생성 유틸리티."""

import random
import string


def generate_task_id(length: int = 5) -> str:
    """영문+숫자 조합의 짧은 ID 생성. 예: 'a3x9k'"""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))
