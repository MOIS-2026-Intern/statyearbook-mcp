# -*- coding: utf-8 -*-
"""pgvector 값을 다루는 공용 변환 함수."""


# 임베딩 벡터를 pgvector 리터럴로 바꾼다.
def vector_literal(values: list[float]) -> str:
    items = ",".join(str(float(value)) for value in values)
    return f"[{items}]"
