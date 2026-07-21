"""관리자 적재 SQL 생성기가 함께 사용하는 PostgreSQL literal 변환."""


# Python 값을 이스케이프된 PostgreSQL 리터럴로 직렬화하고 선택적으로 형변환한다.
def sql_literal(value, cast: str | None = None) -> str:
    if value is None:
        literal = "NULL"
    elif isinstance(value, bool):
        literal = "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        literal = str(value)
    else:
        literal = "'" + str(value).replace("'", "''") + "'"
    return f"{literal}::{cast}" if cast and value is not None else literal
